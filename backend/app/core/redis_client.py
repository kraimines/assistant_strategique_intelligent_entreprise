"""Async Redis client — module-level singleton, consistent with SQLAlchemy engine pattern."""
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Return the module-level singleton Redis client.

    Lazily initialised on first call. Redis down at startup does not
    abort the application — callers must handle connection errors.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency — yields the async Redis client."""
    return get_redis_client()
