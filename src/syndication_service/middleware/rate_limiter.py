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


def client_ip_key(request: Request) -> str:
    """レート制限のキーに使うクライアント IP を返す。

    Cloud Run 等のプロキシ背後では ``request.client.host`` が常に Google Front End
    の IP になり、全リクエストが同一キー（実質グローバルバケット）になってしまう。
    そこで ``X-Forwarded-For`` の先頭（オリジナルクライアント）を優先採用する。

    注: XFF はクライアントが詐称可能。厳密な DoS 防御には Load Balancer +
    Cloud Armor 等で検証済みの XFF を使うのが望ましい。本ポータルは公開 GET 中心の
    ため、現実的な緩和としてこの方式（global バケットよりは確実に改善）を採る。
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return get_remote_address(request)


def create_limiter(
    redis_url: str | None = None,
    default_limits: list[str] | None = None,
    fallback_to_memory: bool = False,
) -> Limiter | None:
    """
    Create a slowapi Limiter instance.

    Args:
        redis_url: Redis connection URL for rate limit storage.
                   If None, uses REDIS_URL environment variable.
                   テスト用 ``memory://`` の場合は ping をスキップして即返す。
        default_limits: デコレータの無いルートにも middleware 経由で適用する既定の
                   レート制限（例: ``["120/minute"]``）。公開 GET API を一括で
                   スロットルするために使う。None なら従来通り既定制限なし。
        fallback_to_memory: Redis 不到達のとき、None（制限完全無効）ではなく
                   ``memory://``（per-instance の in-memory 制限）にフォールバック
                   するか。本番で Redis 未設定でも最低限の制限を効かせるために使う。
                   既定 False は従来どおり None を返す（後方互換）。

    Returns:
        Limiter instance, or None if Redis is unavailable and fallback_to_memory=False.
    """
    try:
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        # Memory backend (テスト用) は接続テスト不要
        is_memory_backend = redis_url.startswith("memory://")

        # 本番では Redis 不到達でも Limiter を生成しておくとリクエスト時に
        # 内部で connection error を投げて 500 になる。事前 ping で到達性を確認し、
        # 不到達なら fallback_to_memory に応じて memory:// 化 or フェイルオープン。
        if not is_memory_backend:
            import redis as _redis

            try:
                client = _redis.Redis.from_url(redis_url, socket_connect_timeout=2)
                client.ping()
                client.close()
            except Exception as ping_error:
                if fallback_to_memory:
                    # per-instance の in-memory バケットで制限を効かせる。複数
                    # インスタンス間では共有されないが、None（完全無効）より確実な緩和。
                    logger.warning(
                        f"Redis ping failed ({redis_url}): {ping_error}. "
                        "Falling back to in-memory rate limiting (per-instance)."
                    )
                    redis_url = "memory://"
                    is_memory_backend = True
                else:
                    logger.warning(
                        f"Redis ping failed ({redis_url}): {ping_error}. "
                        "Rate limiting will be disabled (graceful degradation)."
                    )
                    return None

        # Create limiter with Redis (or memory) storage
        limiter = Limiter(
            key_func=client_ip_key,
            storage_uri=redis_url,
            strategy="fixed-window",
            headers_enabled=True,  # Enable X-RateLimit-* headers
            default_limits=default_limits or [],
        )

        logger.info(
            f"Rate limiter initialized: {redis_url} (default_limits={default_limits or []})"
        )
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

# 公開GET API 全体に適用する既定レート制限（per-IP, per-route）。
# 通常の閲覧では超えない値だが、全件高速吸い出し/L7 フラッドはこれで抑える。
PUBLIC_API_DEFAULT_RATE_LIMIT = os.getenv("ONECO_PUBLIC_API_RATE_LIMIT", "120/minute")
