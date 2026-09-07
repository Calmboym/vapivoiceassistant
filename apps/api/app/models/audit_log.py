from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, _utcnow


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail (§70). Every sensitive action (booking
    created/cancelled/modified, passenger updated, payment created, admin
    login, role changed, human transfer, ...) writes one row here. Never
    put secrets in `event_metadata` — it goes through the same redaction
    expectations as structured logs (see app/core/logging.py)."""

    __tablename__ = "audit_logs"

    actor: Mapped[str] = mapped_column(String(120), nullable=False)  # e.g. "vapi_call:abc123", "admin:jdoe"
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # customer|admin|system|ai_agent
    action: Mapped[str] = mapped_column(String(80), nullable=False)  # e.g. "booking.cancelled"
    resource: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "booking"
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    call_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    event_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.action} {self.resource}:{self.resource_id}>"
