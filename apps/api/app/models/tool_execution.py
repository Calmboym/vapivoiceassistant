from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, _utcnow


class ToolExecution(Base, UUIDPrimaryKeyMixin):
    """One row per Vapi tool-call attempt (Phase 5) — the "existing tool
    execution model" this phase's brief asked to identify (there wasn't
    one; this is it). Append-only, like AuditLog (Phase 4) — created
    once per attempt, never updated — which is why, also like AuditLog,
    it has only `created_at` and not a full TimestampMixin.

    This table and AuditLog serve different purposes and neither
    replaces the other: AuditLog is the cross-channel record of WHAT
    HAPPENED to a resource (an admin's booking edit and a Vapi caller's
    booking edit both produce an AuditLog row, in the same table,
    queryable together). ToolExecution is Vapi-specific and answers a
    narrower, voice-channel question — "what did the ASSISTANT attempt,
    and did we let it" — including attempts that never touched a
    resource at all because authorize_vapi_tool_call() denied them
    first. app/api/routes/vapi.py's webhook handler writes a
    ToolExecution row for every tool call it receives, allowed or
    denied, implemented or not — then, separately, for tool calls that
    actually mutate something, also calls record_audit_event() exactly
    as the web routes already do (see app/services/audit_service.py),
    passing this row's call_id through as AuditLog.call_id.

    `arguments_redacted` stores the tool call's mapped arguments run
    through app.core.security.redaction.redact_value() before being
    persisted — never the raw arguments — so a verification_token or
    anything else matching SENSITIVE_KEY_PATTERN never lands in this
    table in plaintext. This is a debugging/audit log, not a functional-
    security store (that's VerificationSession, which legitimately needs
    a token_hash); it should be safe to hand a staff member the contents
    of this table without also handing them a live bearer credential.
    """

    __tablename__ = "tool_executions"

    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id"), nullable=False, index=True)
    # Vapi's own toolCallId. Unique — this is the transport-level dedup
    # key (did Vapi's webhook delivery retry the exact same tool call
    # because our response was slow/lost), which is a different concern
    # from derive_idempotency_key()'s business-level dedup below (did the
    # LLM ask us to cancel the same booking twice). Both matter; neither
    # substitutes for the other.
    vapi_tool_call_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    arguments_redacted: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # "allowed" | "denied" — the authorize_vapi_tool_call() decision.
    authorization_result: Mapped[str] = mapped_column(String(20), nullable=False)
    denial_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # AuthErrorCode.value, when denied

    # "success" | "error" | "not_implemented" — outcome of actually
    # running the tool, only meaningful when authorization_result ==
    # "allowed". "not_implemented" is distinct from "error": it means
    # tool_schemas.py's `implemented=False` short-circuit fired, not that
    # a real backend call was attempted and failed.
    outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ToolExecution {self.id} tool={self.tool_name} auth={self.authorization_result} outcome={self.outcome}>"
