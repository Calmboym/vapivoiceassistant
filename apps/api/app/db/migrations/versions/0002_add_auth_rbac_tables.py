"""add auth/RBAC/verification tables (Phase 4)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_VERIFICATION"),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("customer_id", sa.Uuid, sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_customer_id", "users", ["customer_id"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("user_agent_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_session_token_hash", "sessions", ["session_token_hash"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(30), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_permissions_name", "permissions", ["name"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("role_id", sa.Uuid, sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("permission_id", sa.Uuid, sa.ForeignKey("permissions.id"), nullable=False),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    op.create_table(
        "user_roles",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role_id", sa.Uuid, sa.ForeignKey("roles.id"), nullable=False),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    op.create_table(
        "verification_sessions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("call_id", sa.String(100), nullable=True),
        sa.Column("booking_id", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="VERIFICATION_PENDING"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verification_sessions_call_id", "verification_sessions", ["call_id"])
    op.create_index("ix_verification_sessions_booking_id", "verification_sessions", ["booking_id"])
    op.create_index("ix_verification_sessions_token_hash", "verification_sessions", ["token_hash"], unique=True)

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])
    op.create_index(
        "ix_email_verification_tokens_token_hash", "email_verification_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_table("email_verification_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("verification_sessions")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("sessions")
    op.drop_table("users")
