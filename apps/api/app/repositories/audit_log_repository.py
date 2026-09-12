from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditLogRepository:
    """No `add()` method here, deliberately — every AuditLog row in this
    codebase is written through app.services.audit_service.
    record_audit_event(), never through this repository. This class
    exists purely to give the admin dashboard (Phase 9 — T-6) a read
    path onto a table that, before this task, had a writer but no
    reader anywhere in the codebase."""

    def __init__(self, db: Session):
        self.db = db

    def list_for_resource(self, resource: str, resource_id: str, *, limit: int = 200) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.resource == resource, AuditLog.resource_id == resource_id)
            .order_by(AuditLog.created_at.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))
