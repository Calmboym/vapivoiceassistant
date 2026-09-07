"""
Thin persistence layer on top of app.core.security.rbac (§7/§8/§30). The
*matrix* (which permissions a role grants) is that module's
ROLE_PERMISSIONS dict — pure, dependency-free, unit-tested. This service
only knows two things the matrix can't: which roles a given user
actually has (from the `user_roles` table), and how to change that.
Turning "these role names" into "this set of permissions" is always
delegated to app.core.security.rbac.permissions_for_roles(), never
reimplemented here.
"""

from __future__ import annotations

from typing import FrozenSet

from sqlalchemy.orm import Session

from app.core.security.rbac import permissions_for_roles
from app.repositories.rbac_repository import RbacRepository
from app.services.audit_service import record_audit_event


class RBACService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = RbacRepository(db)

    def roles_for_user(self, user_id) -> FrozenSet[str]:
        return frozenset(self.repo.role_names_for_user(user_id))

    def permissions_for_user(self, user_id) -> FrozenSet[str]:
        roles = self.roles_for_user(user_id)
        if not roles:
            return frozenset()
        return permissions_for_roles(roles)

    def assign_role(self, user_id, role_name: str, *, actor: str = "system", request_id: str | None = None) -> None:
        self.repo.assign_role(user_id, role_name)
        record_audit_event(
            self.db, actor=actor, actor_type="admin", action="rbac.role_assigned",
            resource="user", resource_id=str(user_id), request_id=request_id, metadata={"role": role_name},
        )

    def revoke_role(self, user_id, role_name: str, *, actor: str = "system", request_id: str | None = None) -> None:
        self.repo.revoke_role(user_id, role_name)
        record_audit_event(
            self.db, actor=actor, actor_type="admin", action="rbac.role_revoked",
            resource="user", resource_id=str(user_id), request_id=request_id, metadata={"role": role_name},
        )
