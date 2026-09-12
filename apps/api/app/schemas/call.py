from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import PageMeta


class CallOut(BaseModel):
    id: str
    vapi_call_id: str
    assistant_id: Optional[str] = None
    direction: Optional[str] = None
    customer_phone_number: Optional[str] = None
    status: str
    ended_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime


class ToolExecutionOut(BaseModel):
    """`arguments` is ToolExecution.arguments_redacted verbatim — already
    scrubbed through app.core.security.redaction.redact_value() at WRITE
    time (see that model's docstring: "it should be safe to hand a staff
    member the contents of this table without also handing them a live
    bearer credential"). This schema does not re-redact; it trusts the
    write-time guarantee, same as every other read path in this codebase
    trusts a field that was already validated/sanitized before it was
    persisted."""

    id: str
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    authorization_result: str
    denial_reason: Optional[str] = None
    outcome: Optional[str] = None
    error_code: Optional[str] = None
    latency_ms: Optional[int] = None
    created_at: datetime


class CallDetailOut(CallOut):
    tool_executions: list[ToolExecutionOut] = Field(default_factory=list)


class CallListOut(BaseModel):
    items: list[CallOut]
    page: PageMeta
