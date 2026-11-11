"""Redis-based rate limiting with automatic in-memory fallback."""

import logging
import time
from collections import defaultdict

import redis.asyncio as aioredis
from fastapi import Request

from app.core.config import settings
from app.core.errors import AppException

logger = logging.getLogger("incidentlens.rate_limit")


class RateLimitExceededError(AppException):
    def __init__(self, message: str = "Rate limit exceeded. Please try again later."):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
        )


# In-memory fallback tracker: key -> list of timestamps
_in_memory_records: dict[str, list[float]] = defaultdict(list)
_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Retrieve or lazily initialize the async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
    return _redis_client


async def check_rate_limit(
    key: str,
    max_requests: int = 10,
    window_seconds: int = 60,
) -> bool:
    """Check if request rate is within limit. Returns True if allowed, False if exceeded."""
    now = time.time()
    redis_available = False

    if not (settings.ENVIRONMENT == "test" or settings.REDIS_URL.startswith("memory")):
        try:
            client = get_redis_client()
            current_count = await client.incr(key)
            if current_count == 1:
                await client.expire(key, window_seconds)
            redis_available = True
            return current_count <= max_requests
        except Exception as exc:
            logger.debug(f"Redis rate limiter failed, falling back to memory: {exc}")

    if not redis_available:
        # Sliding window in-memory fallback
        timestamps = _in_memory_records[key]
        cutoff = now - window_seconds
        # Remove expired timestamps
        _in_memory_records[key] = [ts for ts in timestamps if ts > cutoff]
        if len(_in_memory_records[key]) >= max_requests:
            return False
        _in_memory_records[key].append(now)
        return True

    return True


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request, considering proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def reset_rate_limits() -> None:
    """Helper to clear in-memory rate limits (primarily for testing)."""
    _in_memory_records.clear()
