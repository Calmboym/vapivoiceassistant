"""add Vapi call/tool-execution tables (Phase 5)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("vapi_call_id", sa.String(100), nullable=False, unique=True),
        sa.Column("assistant_id", sa.String(100), nullable=True),
        sa.Column("phone_number_id", sa.String(100), nullable=True),
        sa.Column("direction", sa.String(20), nullable=True),
        sa.Column("customer_phone_number", sa.String(32), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="in_progress"),
        sa.Column("ended_reason", sa.String(100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_calls_vapi_call_id", "calls", ["vapi_call_id"], unique=True)

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("call_id", sa.Uuid, sa.ForeignKey("calls.id"), nullable=False),
        sa.Column("vapi_tool_call_id", sa.String(100), nullable=False, unique=True),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("arguments_redacted", sa.JSON, nullable=False),
        sa.Column("authorization_result", sa.String(20), nullable=False),
        sa.Column("denial_reason", sa.String(100), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tool_executions_call_id", "tool_executions", ["call_id"])
    op.create_index("ix_tool_executions_vapi_tool_call_id", "tool_executions", ["vapi_tool_call_id"], unique=True)
    op.create_index("ix_tool_executions_tool_name", "tool_executions", ["tool_name"])
    op.create_index("ix_tool_executions_idempotency_key", "tool_executions", ["idempotency_key"])


def downgrade() -> None:
    op.drop_table("tool_executions")
    op.drop_table("calls")
