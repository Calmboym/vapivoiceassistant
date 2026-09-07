"""
Redis is used for short-lived call state, idempotency locks, rate limiting,
and cached search results (§29) — never as the source of truth for a
booking; PostgreSQL is authoritative.

get_redis() returns a real redis.Redis client when REDIS_URL is configured
and the `redis` package is installed; otherwise it returns an in-process
fallback with the same get/set/setex/incr surface so local development and
this sandbox can run without a Redis server. The fallback is single-process
only — do not rely on it for anything beyond local dev, per the warning in
app/core/idempotency.py.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class InProcessRedisFallback:
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, Optional[float]]] = {}

    def _expired(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return True
        _, expires_at = entry
        return expires_at is not None and expires_at < time.time()

    def get(self, key: str) -> Optional[str]:
        if self._expired(key):
            self._store.pop(key, None)
            return None
        return self._store[key][0]

    def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        expires_at = time.time() + ex if ex else None
        self._store[key] = (value, expires_at)
        return True

    def setex(self, key: str, seconds: int, value: str) -> bool:
        return self.set(key, value, ex=seconds)

    def incr(self, key: str) -> int:
        current = int(self.get(key) or 0) + 1
        self.set(key, str(current))
        return current

    def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0

    def ping(self) -> bool:
        return True


@lru_cache
def get_redis():
    settings = get_settings()
    if settings.redis_url:
        try:
            import redis  # imported lazily — not a hard dependency in mock/dev mode

            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception as exc:  # noqa: BLE001 — deliberately broad: any failure -> safe fallback
            logger.warning("redis_unavailable_falling_back", error=str(exc))
    return InProcessRedisFallback()
