"""
Redis-backed store for app.core.security.rate_limiter (§17). The pure
algorithm never imports redis; this is the one adapter that does, built
on app.db.redis_client.get_redis() — which already transparently falls
back to an in-process store when REDIS_URL is unset, same pattern
app.core.idempotency uses. Swapping backends never touches the algorithm
itself; see tests/test_security_core.py for the (dependency-free) proof
that the algorithm is correct independent of which store backs it.
"""

from __future__ import annotations

import json
from typing import Optional

from app.core.security.rate_limiter import FailureState
from app.db.redis_client import get_redis


class RedisRateLimitStore:
    """Implements the Protocol rate_limiter.py's FixedWindowRateLimiter
    and BackoffLockout depend on (get_window/increment_window/
    get_failure_state/set_failure_state/clear_failure_state), against
    whatever get_redis() returns — a real redis.Redis client or the
    in-process InProcessRedisFallback both expose the same
    get/set/delete surface (see app/db/redis_client.py), so this class
    doesn't need to know which one it has."""

    def __init__(self):
        self.client = get_redis()

    def get_window(self, key: str, now: float) -> tuple[int, float]:
        raw = self.client.get(f"rl:window:{key}")
        if raw is None:
            return 0, now
        count_str, started_at_str = raw.split(":", 1)
        return int(count_str), float(started_at_str)

    def increment_window(self, key: str, now: float, window_seconds: float) -> tuple[int, float]:
        count, started_at = self.get_window(key, now)
        if now - started_at >= window_seconds:
            count, started_at = 0, now
        count += 1
        self.client.set(f"rl:window:{key}", f"{count}:{started_at}", ex=int(window_seconds) + 5)
        return count, started_at

    def get_failure_state(self, key: str) -> Optional[FailureState]:
        raw = self.client.get(f"rl:failures:{key}")
        if raw is None:
            return None
        data = json.loads(raw)
        return FailureState(consecutive_failures=data["consecutive_failures"], locked_until=data["locked_until"])

    def set_failure_state(self, key: str, state: FailureState) -> None:
        payload = json.dumps({"consecutive_failures": state.consecutive_failures, "locked_until": state.locked_until})
        # One day is a generous outer bound — failures older than that
        # are forgiven even without an explicit clear() call.
        self.client.set(f"rl:failures:{key}", payload, ex=60 * 60 * 24)

    def clear_failure_state(self, key: str) -> None:
        self.client.delete(f"rl:failures:{key}")
