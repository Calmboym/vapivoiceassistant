from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Call(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A phone call handled by the Vapi voice agent (Phase 5).

    One row per Vapi `call.id` — created (or looked up, on Vapi's
    occasional webhook retries) the first time a `tool-calls` message
    arrives for a given call_id, and updated as the call progresses.
    Exists for the same reason VerificationSession does (see that
    model's docstring): each tool invocation in one phone call is a
    separate, stateless HTTP request, and staff/audit visibility into
    "what happened on this call" has nowhere else to live.

    `vapi_call_id` — not `id` — is what the rest of the system joins
    against: AuditLog.call_id and VerificationSession.call_id (both
    Phase 4) already store the raw Vapi call_id as a plain string, not a
    foreign key, and this table keeps that same loose-coupling
    convention rather than retrofitting a real FK onto tables that
    predate this one (see this phase's handoff, Database State, for why
    that retrofit was deliberately not done). ToolExecution.call_id
    below, by contrast, IS a real FK — both tables are new in this same
    migration, so there's no existing schema to disturb.

    Customer phone numbers are stored in plain text here, consistent
    with how contact_email/contact_phone are already handled elsewhere
    in the schema (Customer/booking contact info) — field-level
    encryption in this codebase is reserved specifically for passport
    numbers (§18), not phone/email generally. Permission-gated via the
    calls.read/calls.manage permissions that already existed in
    app/core/security/rbac.py before this phase.
    """

    __tablename__ = "calls"

    vapi_call_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    assistant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone_number_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # "inbound" | "outbound"
    customer_phone_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="in_progress", nullable=False)  # in_progress | ended
    ended_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Vapi's own end-of-call reason
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Call {self.id} vapi_call_id={self.vapi_call_id} status={self.status}>"
