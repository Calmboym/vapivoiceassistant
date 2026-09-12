"""
Admin-facing call + tool-execution read service (Phase 9 — T-6,
docs/TASK_BOARD.md). Read-only — T-6's scope is explicitly "NOT... any
change to booking/payment/Vapi business logic" (docs/TASK_BOARD.md), and
a Call/ToolExecution row is written exclusively by the Vapi webhook
handler (app/api/routes/vapi.py, Phase 5) — this service never writes
either table.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.call import Call
from app.models.tool_execution import ToolExecution
from app.repositories.call_repository import CallRepository
from app.repositories.tool_execution_repository import ToolExecutionRepository


class CallService:
    def __init__(self, db: Session):
        self.db = db
        self.calls = CallRepository(db)
        self.tool_executions = ToolExecutionRepository(db)

    def get_call(self, call_id: str) -> Call:
        call = self.calls.get_by_id(call_id)
        if call is None:
            raise NotFoundError("CALL_NOT_FOUND", "No call found with that id.")
        return call

    def get_call_with_tool_executions(self, call_id: str) -> "tuple[Call, list[ToolExecution]]":
        call = self.get_call(call_id)
        return call, self.tool_executions.list_for_call(call.id)

    def list_calls(self, *, status: Optional[str] = None, limit: int = 20, offset: int = 0) -> "tuple[list[Call], int]":
        items = self.calls.list_admin(status=status, limit=limit, offset=offset)
        total = self.calls.count_admin(status=status)
        return items, total
