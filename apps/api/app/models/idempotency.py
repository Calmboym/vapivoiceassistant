from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class IdempotencyKeyRecord(Base):
    """Durable counterpart to app.core.idempotency.InMemoryIdempotencyStore —
    survives process restarts and is shared across API instances, unlike
    the in-memory store. See docs/BOOKING_FLOW.md for how services choose
    between the two."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    call_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
