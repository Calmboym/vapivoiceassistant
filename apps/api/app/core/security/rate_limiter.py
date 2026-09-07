"""
Rate limiting and login-failure backoff (Phase 4 spec §17, §18).

Deliberately dependency-free (stdlib only). §17's last line is explicit
about this: "If Redis is unavailable during local unit testing, the pure
rate-limit algorithm must still be testable independently." — this file
is that pure algorithm. `InMemoryRateLimitStore` mirrors the
Protocol/InMemory split already used for idempotency
(app/core/idempotency.py) and Redis (app/db/redis_client.py) in this
codebase: same shape, swap the backing store for Redis in production so
limits are shared across API instances.

Two algorithms, because they answer different questions:
  * FixedWindowRateLimiter  — "how many requests has this key made in the
    current window" (login/register/reset endpoints, Vapi webhook, Vapi
    tools, admin auth — §17's protected list).
  * BackoffLockout          — "how many *consecutive failures* has this
    key had, and is it currently locked out" (§18: temporary, not
    permanent, exponential backoff on repeated auth failures).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from typing import Optional, Protocol


def utcnow() -> float:
    return time.time()


# --- storage protocol -------------------------------------------------


class RateLimitStore(Protocol):
    def get_window(self, key: str, now: float) -> tuple[int, float]:
        """Returns (count_in_window, window_started_at). (0, now) if unseen."""
        ...

    def increment_window(self, key: str, now: float, window_seconds: float) -> tuple[int, float]:
        """Increments the count for `key`, starting a fresh window if the
        previous one has expired. Returns the new (count, window_started_at)."""
        ...

    def get_failure_state(self, key: str) -> Optional["FailureState"]:
        ...

    def set_failure_state(self, key: str, state: "FailureState") -> None:
        ...

    def clear_failure_state(self, key: str) -> None:
        ...


@dataclass
class FailureState:
    consecutive_failures: int
    locked_until: Optional[float]  # epoch seconds, or None if not locked


class InMemoryRateLimitStore:
    """Single-process. Production should back this with Redis (same
    shape as app/db/redis_client.py's InProcessRedisFallback) so limits
    survive restarts and apply across multiple API instances."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[int, float]] = {}
        self._failures: dict[str, FailureState] = {}

    def get_window(self, key: str, now: float) -> tuple[int, float]:
        with self._lock:
            return self._windows.get(key, (0, now))

    def increment_window(self, key: str, now: float, window_seconds: float) -> tuple[int, float]:
        with self._lock:
            count, started_at = self._windows.get(key, (0, now))
            if now - started_at >= window_seconds:
                count, started_at = 0, now
            count += 1
            self._windows[key] = (count, started_at)
            return count, started_at

    def get_failure_state(self, key: str) -> Optional[FailureState]:
        with self._lock:
            return self._failures.get(key)

    def set_failure_state(self, key: str, state: FailureState) -> None:
        with self._lock:
            self._failures[key] = state

    def clear_failure_state(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


# --- fixed-window rate limiter ------------------------------------------


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: float


class FixedWindowRateLimiter:
    def __init__(self, store: RateLimitStore, *, limit: int, window_seconds: float):
        self.store = store
        self.limit = limit
        self.window_seconds = window_seconds

    def check(self, key: str, *, now: Optional[float] = None) -> RateLimitResult:
        now = now if now is not None else utcnow()
        count, started_at = self.store.increment_window(key, now, self.window_seconds)
        if count > self.limit:
            retry_after = max(0.0, self.window_seconds - (now - started_at))
            return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=retry_after)
        return RateLimitResult(allowed=True, remaining=self.limit - count, retry_after_seconds=0.0)


# Endpoint-specific defaults (§17's protected list). Production should
# tune these against real traffic; these are deliberately conservative
# starting points, not load-tested numbers.
RATE_LIMIT_PROFILES: dict[str, tuple[int, float]] = {
    "login": (10, 60.0),                    # 10 attempts / min / key
    "register": (5, 60.0 * 60.0),           # 5 / hour / key (usually per-IP)
    "password_reset_request": (5, 60.0 * 60.0),
    "booking_lookup": (10, 60.0),
    "booking_verification": (5, 60.0 * 10.0),  # tighter — this is the guessing-resistance one (§12)
    "vapi_webhook": (120, 60.0),
    "vapi_tool": (60, 60.0),
    "admin_login": (5, 60.0),
}


def build_rate_limiter(profile: str, store: RateLimitStore) -> FixedWindowRateLimiter:
    limit, window = RATE_LIMIT_PROFILES[profile]
    return FixedWindowRateLimiter(store, limit=limit, window_seconds=window)


# --- backoff lockout (§18) ------------------------------------------------


class BackoffLockout:
    """Temporary, exponentially-increasing lockout after repeated
    failures against the same key (typically `login:{email_hash}` or
    `verify:{booking_id}`). Never permanent — `max_backoff_seconds` caps
    it, and a single success clears the counter entirely."""

    def __init__(
        self,
        store: RateLimitStore,
        *,
        threshold: int = 5,
        base_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 15 * 60.0,
    ):
        self.store = store
        self.threshold = threshold
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

    def is_locked(self, key: str, *, now: Optional[float] = None) -> RateLimitResult:
        now = now if now is not None else utcnow()
        state = self.store.get_failure_state(key)
        if state is None or state.locked_until is None:
            return RateLimitResult(allowed=True, remaining=self.threshold, retry_after_seconds=0.0)
        if now >= state.locked_until:
            return RateLimitResult(allowed=True, remaining=self.threshold, retry_after_seconds=0.0)
        return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=state.locked_until - now)

    def record_failure(self, key: str, *, now: Optional[float] = None) -> FailureState:
        now = now if now is not None else utcnow()
        state = self.store.get_failure_state(key) or FailureState(consecutive_failures=0, locked_until=None)
        state.consecutive_failures += 1
        if state.consecutive_failures >= self.threshold:
            # Exponential backoff beyond the threshold: threshold-th
            # failure -> base, +1 -> 2x, +2 -> 4x, ... capped.
            exponent = state.consecutive_failures - self.threshold
            backoff = min(self.base_backoff_seconds * (2 ** exponent), self.max_backoff_seconds)
            state.locked_until = now + backoff
        self.store.set_failure_state(key, state)
        # Return a SNAPSHOT, not the mutable object the store holds:
        # get_failure_state()/set_failure_state() round-trip the same
        # FailureState reference (InMemoryRateLimitStore does no
        # copying), so a caller that keeps the return value of two
        # successive record_failure() calls would otherwise find both
        # variables pointing at the same, further-mutated object — found
        # by test_backoff_increases_and_is_capped actually comparing two
        # "different" results and getting identical values, not by
        # inspection.
        return replace(state)

    def record_success(self, key: str) -> None:
        self.store.clear_failure_state(key)
