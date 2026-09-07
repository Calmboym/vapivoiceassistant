from __future__ import annotations

from typing import Optional

from sqlalchemy import select
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
