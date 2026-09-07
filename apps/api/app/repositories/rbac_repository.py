from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rbac import Permission, Role, RolePermission, UserRole


class RbacRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_role_by_name(self, name: str) -> Optional[Role]:
        return self.db.scalar(select(Role).where(Role.name == name))

    def get_permission_by_name(self, name: str) -> Optional[Permission]:
        return self.db.scalar(select(Permission).where(Permission.name == name))

    def role_names_for_user(self, user_id) -> list[str]:
        rows = self.db.scalars(
            select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        )
        return list(rows)

    def assign_role(self, user_id, role_name: str) -> None:
        role = self.get_role_by_name(role_name)
        if role is None:
            raise ValueError(f"Unknown role {role_name!r} — has app/db/seed.py been run for this database?")
        already = self.db.scalar(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
        )
        if already is not None:
            return
        self.db.add(UserRole(user_id=user_id, role_id=role.id))
        self.db.flush()

    def revoke_role(self, user_id, role_name: str) -> None:
        role = self.get_role_by_name(role_name)
        if role is None:
            return
        existing = self.db.scalar(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
        )
        if existing is not None:
            self.db.delete(existing)
            self.db.flush()

    def upsert_role(self, name: str, *, description: Optional[str] = None) -> Role:
        """Used by app/db/seed.py to load app.core.security.rbac.Role
        into the roles table idempotently."""
        role = self.get_role_by_name(name)
        if role is not None:
            return role
        role = Role(name=name, description=description)
        self.db.add(role)
        self.db.flush()
        return role

    def upsert_permission(self, name: str, *, description: Optional[str] = None) -> Permission:
        permission = self.get_permission_by_name(name)
        if permission is not None:
            return permission
        permission = Permission(name=name, description=description)
        self.db.add(permission)
        self.db.flush()
        return permission

    def set_role_permissions(self, role: Role, permission_names: frozenset) -> None:
        existing = self.db.scalars(select(RolePermission).where(RolePermission.role_id == role.id))
        for row in existing:
            self.db.delete(row)
        self.db.flush()
        for name in permission_names:
            permission = self.upsert_permission(name)
            self.db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        self.db.flush()
