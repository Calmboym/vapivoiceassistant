from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# The authoritative role/permission *matrix* (which permissions a role
# grants by default) lives in app.core.security.rbac, dependency-free and
# unit-tested on its own. These tables are what actually gets *assigned*
# at runtime — app/db/seed.py loads app.core.security.rbac's
# ROLE_PERMISSIONS into them on a fresh install (§8/§30).


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class Permission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id"), nullable=False, index=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("permissions.id"), nullable=False, index=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id"), nullable=False, index=True)

    user: Mapped["User"] = relationship(back_populates="role_assignments")
    role: Mapped["Role"] = relationship()
