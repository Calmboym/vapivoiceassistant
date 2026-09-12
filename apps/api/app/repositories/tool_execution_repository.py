from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tool_execution import ToolExecution


class ToolExecutionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_vapi_tool_call_id(self, vapi_tool_call_id: str) -> Optional[ToolExecution]:
        """Transport-level dedup lookup — see ToolExecution's docstring
        on how this differs from business-level idempotency."""
        return self.db.scalar(select(ToolExecution).where(ToolExecution.vapi_tool_call_id == vapi_tool_call_id))

    def add(self, execution: ToolExecution) -> ToolExecution:
        self.db.add(execution)
        self.db.flush()
        return execution

    # --- Phase 9 (T-6) admin dashboard addition below ---

    def list_for_call(self, call_id) -> list[ToolExecution]:
        """Every tool-call attempt on one call, oldest first — allowed
        AND denied, implemented AND not (see this model's own docstring)
        — this is the staff-facing "what did the assistant try to do on
        this call" view, so it must show the full attempt history, not
        just the successful ones."""
        stmt = select(ToolExecution).where(ToolExecution.call_id == call_id).order_by(ToolExecution.created_at.asc())
        return list(self.db.scalars(stmt))
