"""add payment refund-tracking columns (T-3 — refund_payment)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-08

Deliberately does NOT touch `payments.status`'s existing vocabulary or
any check constraint on it — see app/models/payment.py's refund-tracking
comment for why a refund is modeled as new, separate columns rather than
a new `status` value.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("provider_refund_id", sa.String(255), nullable=True))
    op.add_column("payments", sa.Column("refunded_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("payments", sa.Column("refund_status", sa.String(20), nullable=True))
    op.add_column("payments", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("refund_reason", sa.String(255), nullable=True))
    op.create_index("ix_payments_provider_refund_id", "payments", ["provider_refund_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_provider_refund_id", table_name="payments")
    op.drop_column("payments", "refund_reason")
    op.drop_column("payments", "refunded_at")
    op.drop_column("payments", "refund_status")
    op.drop_column("payments", "refunded_amount")
    op.drop_column("payments", "provider_refund_id")
