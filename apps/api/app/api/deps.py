from __future__ import annotations

from functools import lru_cache

from app.core.idempotency import IdempotencyStore, InMemoryIdempotencyStore
from app.providers.airline import get_airline_provider  # re-exported for route imports
from app.providers.airline.base import AirlineProvider
from app.providers.payments import get_payment_provider  # re-exported for route imports
from app.providers.payments.base import PaymentProvider

__all__ = [
    "get_airline_provider", "get_idempotency_store", "AirlineProvider",
    "get_payment_provider", "PaymentProvider",
]


@lru_cache
def get_idempotency_store() -> IdempotencyStore:
    # Single-process default. Production should swap this for a
    # Redis-backed implementation built on app/db/redis_client.py so
    # idempotency survives restarts and works across multiple API
    # instances — see the warning in app/core/idempotency.py.
    return InMemoryIdempotencyStore()
