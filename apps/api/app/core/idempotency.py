"""
Idempotency for transactional voice-tool operations (§27).

A Vapi tool call can legitimately be retried (flaky network, agent restart,
customer repeating themselves mid-call) — retrying `create_booking` must
never create a second booking. The key is derived from
(call_id, operation, canonical request payload) so the *same* logical
request always maps to the *same* key, and a stored result is replayed
instead of re-executing the operation.

`InMemoryIdempotencyStore` is what runs in this sandbox / single-process
dev. Production must back this with Redis (see app/db/redis_client.py) so
it survives process restarts and works across multiple API instances —
swap the implementation, keep the same Protocol.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol


def derive_idempotency_key(call_id: str, operation: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{call_id}:{operation}:{canonical}".encode("utf-8")).hexdigest()
    return f"idem_{digest[:32]}"


@dataclass
class StoredResult:
    status: str  # "in_progress" | "completed" | "failed"
    result: Optional[dict[str, Any]]
    created_at: float


class IdempotencyStore(Protocol):
    def begin(self, key: str) -> Optional[StoredResult]:
        """Returns the existing StoredResult if this key was already seen,
        else registers it as in_progress and returns None (caller should
        proceed with the operation)."""
        ...

    def complete(self, key: str, result: dict[str, Any]) -> None: ...

    def fail(self, key: str) -> None:
        """Clears the in-progress marker so a genuinely failed operation can
        be retried under the same key rather than being stuck forever."""
        ...


class InMemoryIdempotencyStore:
    """Dev/single-process implementation. NOT sufficient for a
    multi-instance production deployment — see module docstring."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, StoredResult] = {}

    def begin(self, key: str) -> Optional[StoredResult]:
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                return existing
            self._entries[key] = StoredResult(status="in_progress", result=None, created_at=time.time())
            return None

    def complete(self, key: str, result: dict[str, Any]) -> None:
        with self._lock:
            self._entries[key] = StoredResult(status="completed", result=result, created_at=time.time())

    def fail(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)
