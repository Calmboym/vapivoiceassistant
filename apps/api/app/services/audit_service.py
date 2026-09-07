from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record_audit_event(
    db: Session,
    *,
    actor: str,
    actor_type: str,
    action: str,
    resource: str,
    resource_id: Optional[str] = None,
    request_id: Optional[str] = None,
    call_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        actor_type=actor_type,
        action=action,
        resource=resource,
        resource_id=resource_id,
        request_id=request_id,
        call_id=call_id,
        event_metadata=metadata or {},
    )
    db.add(entry)
    db.flush()
    return entry
