"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "airports",
        sa.Column("iata", sa.String(3), primary_key=True),
        sa.Column("icao", sa.String(4), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "aircraft",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("registration", sa.String(20), nullable=False, unique=True),
        sa.Column("manufacturer", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("aircraft_type", sa.String(20), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("seat_capacity", sa.Integer, nullable=False),
        sa.Column("range_km", sa.Integer, nullable=False),
        sa.Column("baggage_capacity_kg", sa.Integer, nullable=False),
        sa.Column("cabin_configuration", sa.String(100), nullable=False),
        sa.Column("amenities", sa.JSON, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("current_location", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("preferred_language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customers_email", "customers", ["email"], unique=True)
    op.create_index("ix_customers_phone", "customers", ["phone"], unique=False)

    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("pnr", sa.String(6), nullable=False, unique=True),
        sa.Column("provider_booking_reference", sa.String(32), nullable=True),
        sa.Column("provider_name", sa.String(20), nullable=False, server_default="mock"),
        sa.Column("status", sa.String(30), nullable=False, server_default="QUOTE"),
        sa.Column("payment_status", sa.String(20), nullable=False, server_default="UNPAID"),
        sa.Column("customer_id", sa.Uuid, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("origin", sa.String(3), nullable=False),
        sa.Column("destination", sa.String(3), nullable=False),
        sa.Column("flight_number", sa.String(10), nullable=False),
        sa.Column("aircraft_type", sa.String(20), nullable=False),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("base_fare", sa.Numeric(10, 2), nullable=False),
        sa.Column("tax", sa.Numeric(10, 2), nullable=False),
        sa.Column("fees", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("cancellation_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bookings_pnr", "bookings", ["pnr"], unique=True)
    op.create_index("ix_bookings_provider_booking_reference", "bookings", ["provider_booking_reference"])

    op.create_table(
        "booking_passengers",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("booking_id", sa.Uuid, sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("provider_passenger_id", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("middle_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=True),
        sa.Column("passenger_type", sa.String(10), nullable=False, server_default="adult"),
        sa.Column("gender", sa.String(20), nullable=True),
        sa.Column("nationality", sa.String(100), nullable=True),
        sa.Column("passport_number_encrypted", sa.String(500), nullable=True),
        sa.Column("passport_country", sa.String(100), nullable=True),
        sa.Column("passport_expiry", sa.Date, nullable=True),
        sa.Column("frequent_flyer_number", sa.String(50), nullable=True),
        sa.Column("meal_preference", sa.String(50), nullable=True),
        sa.Column("seat_preference", sa.String(50), nullable=True),
        sa.Column("special_assistance", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("call_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_idempotency_keys_call_id", "idempotency_keys", ["call_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("call_id", sa.String(100), nullable=True),
        sa.Column("event_metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])
    op.create_index("ix_audit_logs_call_id", "audit_logs", ["call_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("idempotency_keys")
    op.drop_table("booking_passengers")
    op.drop_table("bookings")
    op.drop_table("customers")
    op.drop_table("aircraft")
    op.drop_table("airports")
