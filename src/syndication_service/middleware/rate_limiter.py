"""
Rate limiter middleware using slowapi.

This module implements IP-based rate limiting for syndication service endpoints.
"""

import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def create_limiter(redis_url: str | None = None) -> Limiter | None:
    """
    Create a slowapi Limiter instance.

    Args:
        redis_url: Redis connection URL for rate limit storage.
                   If None, uses REDIS_URL environment variable.
                   If Redis is unavailable, returns None (graceful degradation).
                   テスト用 ``memory://`` の場合は ping をスキップして即返す。

    Returns:
        Limiter instance or None if Redis is unavailable.
    """
    try:
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        # Memory backend (テスト用) は接続テスト不要
        is_memory_backend = redis_url.startswith("memory://")

        # 本番では Redis 不到達でも Limiter を生成しておくとリクエスト時に
        # 内部で connection error を投げて 500 になる。事前 ping でフェイル
        # オープン化（Limiter なしの no-op 動作）する。
        if not is_memory_backend:
            import redis as _redis

            try:
                client = _redis.Redis.from_url(redis_url, socket_connect_timeout=2)
                client.ping()
                client.close()
            except Exception as ping_error:
                logger.warning(
                    f"Redis ping failed ({redis_url}): {ping_error}. "
                    "Rate limiting will be disabled (graceful degradation)."
                )
                return None

        # Create limiter with Redis (or memory) storage
        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=redis_url,
            strategy="fixed-window",
            headers_enabled=True,  # Enable X-RateLimit-* headers
        )

        logger.info(f"Rate limiter initialized: {redis_url}")
        return limiter

    except Exception as e:
        logger.warning(
            f"Failed to initialize rate limiter: {e}. "
            "Rate limiting will be disabled (graceful degradation)."
        )
        return None


def rate_limit_error_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Handle rate limit exceeded errors.

    Args:
        request: FastAPI request object.
        exc: RateLimitExceeded exception.

    Returns:
        JSONResponse with 429 status code and Retry-After header.
    """
    response = JSONResponse(
        status_code=429,
        content={"detail": "レート制限を超過しました"},
    )

    # Add Retry-After header (60 seconds for 60 req/min limit)
    response.headers["Retry-After"] = "60"

    # Add X-RateLimit-* headers (slowapi adds these automatically)
    return response


# Default rate limit: 60 requests per minute
DEFAULT_RATE_LIMIT = "60/minute"
