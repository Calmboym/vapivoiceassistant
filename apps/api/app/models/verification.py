from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, _utcnow


class VerificationSession(Base, UUIDPrimaryKeyMixin):
    """Durable counterpart to app.core.security.verification's pure state
    machine (§12/§30). Needs its own table (rather than living only in
    memory or Redis) because a Vapi call's tool invocations each arrive
    as separate, stateless HTTP requests spread over the length of a
    phone call — the state has to survive between them. `token_hash`
    mirrors app.core.security.tokens: only the hash of the
    caller-presented token is ever stored."""

    __tablename__ = "verification_sessions"

    call_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    booking_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # Booking.id, stringified
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="VERIFICATION_PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VerificationSession {self.id} booking={self.booking_id} status={self.status}>"
