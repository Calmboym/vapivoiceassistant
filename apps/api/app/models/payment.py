from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.payments.state_machine import PAYMENT_SESSION_STATUSES  # noqa: F401 (re-exported for callers)
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One attempt to collect payment for a booking, via one Stripe
    Checkout Session. A booking may have several Payment rows over time
    (a FAILED/EXPIRED attempt followed by a later SUCCEEDED one) — the
    latest one is authoritative for "is this booking paid" (see
    PaymentRepository.get_latest_for_booking). Never delete/overwrite an
    old row on retry; each attempt is its own audit trail.

    See app/core/payments/state_machine.py for the status vocabulary and
    the allowed transitions between them.
    """

    __tablename__ = "payments"

    booking_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("bookings.id"), nullable=False, index=True)
    booking: Mapped["Booking"] = relationship()  # one-directional — Booking model is untouched by this milestone

    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id"), nullable=False, index=True)

    provider_name: Mapped[str] = mapped_column(String(20), default="stripe", nullable=False)
    # Stripe's Checkout Session id (cs_...). Populated at creation time —
    # we always have it before the row is ever inserted, since the
    # provider call happens first (see PaymentService.create_payment_
    # session) — but left nullable rather than NOT NULL so a future
    # provider that genuinely creates the local row first isn't blocked
    # by this schema.
    provider_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)
    # Populated once Stripe attaches a PaymentIntent to the session
    # (immediately for card payments; on completion for some other
    # methods) — kept distinct from provider_session_id because refunds
    # (staff-only `refund_payment`, T-3) act on the PaymentIntent, not
    # the Checkout Session.
    provider_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)

    # The AUTHORITATIVE amount, snapshotted from Booking.total_price at
    # the moment this session was created — never taken from the
    # request/LLM (see PaymentSessionCreateRequest's docstring). Snapshot,
    # not a live reference: if the booking's price were ever to change
    # after this session was created (modify_booking can change
    # total_price), an in-flight payment session must keep charging what
    # the customer actually saw and agreed to when they started paying,
    # not a value that moved under them mid-checkout.
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # Defense in depth alongside app.core.idempotency.IdempotencyStore
    # (see that module's docstring on why the in-memory implementation
    # alone isn't multi-instance-safe): a DB-level UNIQUE constraint here
    # means even a process-restart race that slipped past the in-memory
    # check can't produce two Payment rows for the same logical request —
    # the second INSERT simply fails at the database.
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    checkout_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Populated only on FAILED — never logged/spoken with more detail
    # than this (see docs/PAYMENTS.md "never expose raw Stripe
    # exceptions"). failure_message is a short, already-user-safe string,
    # same trust level as ProviderError.message elsewhere in this codebase.
    failure_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # --- Refund tracking (T-3 — TASK_BOARD.md) ---
    #
    # Deliberately NOT a new `status` value: `status` above stays
    # "SUCCEEDED" forever once paid — a refund is a fact about the
    # underlying PaymentIntent/Charge, layered on top of an already-
    # terminal Checkout Session, not a change to the session's own
    # lifecycle (see app/core/payments/state_machine.py's docstring,
    # unmodified by this milestone on purpose — see
    # tests.test_payments_core.StateMachineTests.
    # test_booking_payment_status_mapping_never_produces_refunded, which
    # this design keeps true rather than needing to update). A booking's
    # own REFUNDED status still lives on Booking.payment_status exactly
    # as before (app/models/booking.py's pre-existing PAYMENT_STATUSES) —
    # set by PaymentService.refund_payment / CancellationService.cancel,
    # never by anything here.
    #
    # A Payment can be refunded more than once (partial, then partial
    # again, up to the total) — these columns hold the CUMULATIVE state
    # of the latest refund attempt, not a list of every attempt. Each
    # individual attempt is still fully recorded in the audit log
    # (action="payment.refunded"/"payment.refund_pending"/
    # "payment.refund_failed", resource_id=this Payment's id) — see
    # PaymentService.apply_refund_outcome.
    provider_refund_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    refunded_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    # Stripe's own Refund.status vocabulary, lowercase, on purpose
    # distinct from `status` above's uppercase session-status vocabulary
    # — see RefundStatus in app/providers/payments/base.py.
    refund_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Free-text, staff-supplied (standalone refund_payment route) or a
    # fixed system value ("booking_cancelled" — CancellationService's
    # auto-refund). Never rendered back to a customer verbatim without
    # review — same caution as failure_message above.
    refund_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment {self.id} {self.status} {self.amount} {self.currency}>"
