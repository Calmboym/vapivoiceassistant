"""
Admin dashboard — calls routes (Phase 9 — T-6, docs/TASK_BOARD.md).

CALLS_READ is never granted to the bare CUSTOMER role (see rbac.py's
ROLE_PERMISSIONS — only READ_ONLY/SUPPORT_AGENT/ADMIN/SUPER_ADMIN hold
it), so require_permission() alone is already staff-only here — no
require_staff_permission() needed, unlike the customers list route. See
tests/test_security_core.py::RbacTests::
test_customer_role_never_holds_admin_or_calls_permissions, which pins
this as a design assumption this file relies on.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps_auth import require_permission
from app.core.security.actor import CurrentActor
from app.core.security.rbac import Permission
from app.db.session import get_db
from app.models.call import Call
from app.models.tool_execution import ToolExecution
from app.schemas.call import CallDetailOut, CallListOut, CallOut, ToolExecutionOut
from app.schemas.common import make_page_meta, ok
from app.services.call_service import CallService

router = APIRouter(prefix="/api/v1/calls", tags=["calls"])


def _call_out(c: Call) -> CallOut:
    return CallOut(
        id=str(c.id), vapi_call_id=c.vapi_call_id, assistant_id=c.assistant_id, direction=c.direction,
        customer_phone_number=c.customer_phone_number, status=c.status, ended_reason=c.ended_reason,
        started_at=c.started_at, ended_at=c.ended_at, created_at=c.created_at,
    )


def _tool_execution_out(t: ToolExecution) -> ToolExecutionOut:
    return ToolExecutionOut(
        id=str(t.id), tool_name=t.tool_name, arguments=t.arguments_redacted,
        authorization_result=t.authorization_result, denial_reason=t.denial_reason,
        outcome=t.outcome, error_code=t.error_code, latency_ms=t.latency_ms, created_at=t.created_at,
    )


@router.get("")
def list_calls(
    request: Request,
    status: Optional[str] = Query(default=None, max_length=30),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(require_permission(Permission.CALLS_READ.value)),
):
    items, total = CallService(db).list_calls(status=status, limit=limit, offset=offset)
    body = CallListOut(
        items=[_call_out(c) for c in items],
        page=make_page_meta(limit=limit, offset=offset, total=total),
    )
    return ok(body, request.state.request_id)


@router.get("/{call_id}")
def get_call(
    call_id: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(require_permission(Permission.CALLS_READ.value)),
):
    call, tool_executions = CallService(db).get_call_with_tool_executions(call_id)
    body = CallDetailOut(**_call_out(call).model_dump(), tool_executions=[_tool_execution_out(t) for t in tool_executions])
    return ok(body, request.state.request_id)
