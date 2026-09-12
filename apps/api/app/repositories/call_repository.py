from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.call import Call


class CallRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_vapi_call_id(self, vapi_call_id: str) -> Optional[Call]:
        return self.db.scalar(select(Call).where(Call.vapi_call_id == vapi_call_id))

    def add(self, call: Call) -> Call:
        self.db.add(call)
        self.db.flush()
        return call

    # --- Phase 9 (T-6) admin dashboard additions below ---

    def get_by_id(self, call_id) -> Optional[Call]:
        """Internal UUID primary key — NOT vapi_call_id (see
        get_by_vapi_call_id above for that). Staff browsing the admin
        dashboard navigate by this table's own id; the Vapi webhook
        handler is the only caller that ever looks a call up by its
        Vapi-assigned id instead."""
        return self.db.get(Call, call_id)

    def list_admin(self, *, status: Optional[str] = None, limit: int = 20, offset: int = 0) -> list[Call]:
        stmt = select(Call).order_by(Call.created_at.desc())
        if status:
            stmt = stmt.where(Call.status == status)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def count_admin(self, *, status: Optional[str] = None) -> int:
        stmt = select(func.count()).select_from(Call)
        if status:
            stmt = stmt.where(Call.status == status)
        return self.db.scalar(stmt) or 0
