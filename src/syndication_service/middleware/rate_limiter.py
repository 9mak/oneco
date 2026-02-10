"""
Rate limiter middleware using slowapi.

This module implements IP-based rate limiting for syndication service endpoints.
"""
import logging
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import os

logger = logging.getLogger(__name__)


def create_limiter(redis_url: Optional[str] = None) -> Optional[Limiter]:
    """
    Create a slowapi Limiter instance.

    Args:
        redis_url: Redis connection URL for rate limit storage.
                   If None, uses REDIS_URL environment variable.
                   If Redis is unavailable, returns None (graceful degradation).

    Returns:
        Limiter instance or None if Redis is unavailable.
    """
    try:
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        # Create limiter with Redis storage
        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=redis_url,
            strategy="fixed-window",
            headers_enabled=True,  # Enable X-RateLimit-* headers
        )

        logger.info(f"Rate limiter initialized with Redis storage: {redis_url}")
        return limiter

    except Exception as e:
        logger.warning(
            f"Failed to initialize rate limiter with Redis: {e}. "
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
