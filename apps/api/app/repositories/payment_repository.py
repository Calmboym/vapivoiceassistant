from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.payments.state_machine import TERMINAL_PAYMENT_SESSION_STATUSES
from app.models.payment import Payment


class PaymentRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.flush()  # assigns the PK without committing the outer transaction
        return payment

    def get_by_id(self, payment_id) -> Optional[Payment]:
        return self.db.get(Payment, payment_id)

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Payment]:
        return self.db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))

    def get_by_provider_session_id(self, provider_session_id: str) -> Optional[Payment]:
        return self.db.scalar(select(Payment).where(Payment.provider_session_id == provider_session_id))

    def get_open_for_booking(self, booking_id) -> Optional[Payment]:
        """A non-terminal (PENDING/PROCESSING) Payment for this booking,
        if one exists — used to avoid starting a second concurrent
        Stripe Checkout Session for the same booking when one is already
        in flight. Returns the most recently created if somehow more
        than one is open (shouldn't normally happen, since this check is
        exactly what prevents it — defensive, not load-bearing)."""
        stmt = (
            select(Payment)
            .where(Payment.booking_id == booking_id)
            .where(Payment.status.not_in(TERMINAL_PAYMENT_SESSION_STATUSES))
            .order_by(Payment.created_at.desc())
        )
        return self.db.scalars(stmt).first()

    def get_latest_for_booking(self, booking_id) -> Optional[Payment]:
        stmt = select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.created_at.desc())
        return self.db.scalars(stmt).first()

    def list_for_booking(self, booking_id) -> list[Payment]:
        stmt = select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.created_at.desc())
        return list(self.db.scalars(stmt))
