"""add payments table (Phase 6 Milestone 1 — Stripe)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("booking_id", sa.Uuid, sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("provider_name", sa.String(20), nullable=False, server_default="stripe"),
        sa.Column("provider_session_id", sa.String(255), nullable=True, unique=True),
        sa.Column("provider_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("checkout_url", sa.String(2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(50), nullable=True),
        sa.Column("failure_message", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_provider_session_id", "payments", ["provider_session_id"], unique=True)
    op.create_index("ix_payments_provider_payment_intent_id", "payments", ["provider_payment_intent_id"])
    op.create_index("ix_payments_idempotency_key", "payments", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_table("payments")
