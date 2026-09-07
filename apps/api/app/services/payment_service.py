"""
PaymentService (Phase 6 Milestone 1).

The ONE place payment business logic lives — app/api/routes/payments.py
(web) and app/api/routes/vapi.py's two new dispatch functions (voice)
both call the SAME methods on this class, exactly like BookingService/
CancellationService already do for the rest of the booking lifecycle
(see PROJECT_HANDOFF_PHASE_5's Milestone 1 spec §1/§11: "Do NOT implement
Vapi -> Stripe directly... The same Payment Service must be reusable by
the normal web/API layer.").

This service never calls authorize_*() itself — same pattern as
BookingService/CancellationService: the caller (a route, or
app/api/routes/vapi.py's webhook handler) authorizes BEFORE constructing
the request/calling this service, using whichever gate is appropriate for
that channel (require_payment_access for an authenticated web owner;
authorize_vapi_tool_call's already-registered REQUIRES_VERIFIED_BOOKING
entries for a voice caller). See docs/PAYMENTS.md "Authorization" for the
full reasoning on why two different gates converge on one service.

Idempotency guarantee, stated honestly (Milestone 1 spec §7 — "do not
claim perfect distributed exactly-once semantics if they cannot actually
be guaranteed"):
  - The SAME idempotency_key retried while the first attempt is still
    "in_progress" is rejected with PAYMENT_SESSION_IN_PROGRESS, not
    silently duplicated.
  - The SAME idempotency_key retried after the first attempt completed
    replays the same Payment row — no second Stripe session, no second
    database row.
  - idempotency_key is ALSO passed through to the provider itself
    (StripePaymentProvider forwards it as Stripe's own Idempotency-Key)
    — this is what actually protects against a crash between "Stripe
    created the session" and "we committed the local Payment row": a
    retry with the same key gets Stripe's cached original session back,
    not a second charge-capable session, and this time the local commit
    can succeed. If the process crashes and that key is never retried at
    all, the orphaned Stripe session simply expires after 24h — an
    abandoned checkout page, not a duplicate charge. That is the actual
    guarantee; nothing here claims stronger than that.
  - A DIFFERENT idempotency_key for the same booking while a payment is
    already PENDING/PROCESSING does NOT create a second concurrent
    session — see get_open_for_booking's use below.
  - A genuinely concurrent double-submission (two requests for the same
    booking arriving before either has committed) is not fully closed by
    the in-memory IdempotencyStore alone (documented limitation already
    stated in app/core/idempotency.py) — the UNIQUE constraint on
    Payment.idempotency_key (and, for same-key races, the same one on
    provider_session_id) is the actual backstop: the second INSERT fails
    at the database rather than silently succeeding twice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.idempotency import IdempotencyStore
from app.core.payments.state_machine import (
    BOOKING_PAYMENT_STATUS_FOR_SESSION,
    BOOKING_PAYMENT_STATUSES_BLOCKING_NEW_SESSION,
    RELEVANT_WEBHOOK_EVENT_TYPES,
    can_transition,
    new_status_for_webhook_event,
)
from app.models.booking import Booking
from app.models.payment import Payment
from app.providers.payments.base import PaymentProvider
from app.repositories.booking_repository import BookingRepository
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import PaymentSessionCreateRequest
from app.services.audit_service import record_audit_event


class PaymentService:
    def __init__(self, db: Session, provider: PaymentProvider, idempotency: IdempotencyStore):
        self.db = db
        self.provider = provider
        self.idempotency = idempotency
        self.bookings = BookingRepository(db)
        self.payments = PaymentRepository(db)

    # ------------------------------------------------------------ create

    def create_payment_session(
        self, request: PaymentSessionCreateRequest, *, actor: str, call_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Payment:
        if not request.customer_confirmed:
            # Same ordering/reasoning as CancellationService.cancel() and
            # BookingService.modify_booking(): checked before the booking
            # is even loaded, mirroring the existing convention exactly.
            raise ValidationFailedError(
                "CONFIRMATION_REQUIRED", "Starting a payment requires the customer's explicit yes first."
            )

        booking = self.bookings.get_by_pnr(request.pnr)
        if booking is None:
            raise NotFoundError("BOOKING_NOT_FOUND", f"No booking found for PNR {request.pnr}.")
        if booking.status == "CANCELLED":
            raise ValidationFailedError("BOOKING_NOT_PAYABLE", "This booking has been cancelled and can't be paid for.")

        if booking.payment_status in BOOKING_PAYMENT_STATUSES_BLOCKING_NEW_SESSION:
            if booking.payment_status == "PAID":
                raise ConflictError("PAYMENT_ALREADY_COMPLETED", "This booking has already been paid.")
            if booking.payment_status == "REFUNDED":
                raise ConflictError(
                    "PAYMENT_ALREADY_COMPLETED", "This booking has already been refunded and can't be paid again."
                )
            # payment_status == "PENDING": reuse the existing in-flight
            # session rather than starting a second one for the same
            # booking, regardless of whether this call's idempotency_key
            # matches an earlier one — this is a booking-level guard, not
            # just a request-level one. See module docstring.
            existing_open = self.payments.get_open_for_booking(booking.id)
            if existing_open is not None:
                return existing_open
            # Data drifted (payment_status says PENDING but no open
            # Payment row exists) — fall through and allow a fresh
            # attempt rather than permanently locking the customer out.

        cached = self.idempotency.begin(request.idempotency_key)
        if cached is not None:
            if cached.status == "completed" and cached.result:
                existing = self.payments.get_by_id(cached.result["payment_id"])
                if existing is not None:
                    return existing
            if cached.status == "in_progress":
                raise ValidationFailedError(
                    "PAYMENT_SESSION_IN_PROGRESS", "This payment request is already being processed."
                )

        try:
            # THE authoritative amount — see PaymentSessionCreateRequest's
            # docstring. Snapshotted onto the Payment row, not re-read
            # from Booking later, so an in-flight session keeps charging
            # what the customer actually saw (see app/models/payment.py's
            # `amount` docstring).
            amount = booking.total_price
            currency = booking.currency

            settings = get_settings()
            session = self.provider.create_checkout_session(
                reference=booking.pnr,
                amount=amount,
                currency=currency,
                idempotency_key=request.idempotency_key,
                success_url=f"{settings.frontend_url}/payment/success?pnr={booking.pnr}",
                cancel_url=f"{settings.frontend_url}/payment/cancelled?pnr={booking.pnr}",
                metadata={"booking_id": str(booking.id), "pnr": booking.pnr},
            )

            payment = Payment(
                booking_id=booking.id,
                customer_id=booking.customer_id,
                provider_name=self.provider.name,
                provider_session_id=session.provider_session_id,
                provider_payment_intent_id=session.payment_intent_id,
                status="PENDING",
                amount=amount,
                currency=currency,
                idempotency_key=request.idempotency_key,
                checkout_url=session.checkout_url,
                expires_at=session.expires_at,
            )
            self.payments.add(payment)
            booking.payment_status = "PENDING"

            record_audit_event(
                self.db, actor=actor, actor_type="ai_agent" if call_id else "system",
                action="payment.session_created", resource="payment", resource_id=str(payment.id),
                request_id=request_id, call_id=call_id,
                metadata={
                    "pnr": booking.pnr, "amount": str(amount), "currency": currency,
                    "provider": self.provider.name,
                },
            )
            self.db.commit()
            self.idempotency.complete(request.idempotency_key, {"payment_id": str(payment.id)})
            return payment
        except Exception:
            self.db.rollback()
            self.idempotency.fail(request.idempotency_key)
            raise

    # ------------------------------------------------------------- status

    def get_payment_status(self, pnr: str) -> tuple[Booking, Optional[Payment]]:
        """§8: "The result must come from authoritative backend/provider
        state" — this reads Payment.status as already tracked in our own
        database (kept current by handle_webhook_event below), not a
        live Stripe call on every read, and never anything client-
        supplied. That's still "authoritative backend state," not "trust
        the caller" — see docs/PAYMENTS.md for why a live provider call
        on every status check isn't done here (latency + Stripe rate
        limits for something the webhook already keeps fresh)."""
        booking = self.bookings.get_by_pnr(pnr)
        if booking is None:
            raise NotFoundError("BOOKING_NOT_FOUND", f"No booking found for PNR {pnr}.")
        payment = self.payments.get_latest_for_booking(booking.id)
        return booking, payment

    # ------------------------------------------------------------ webhook

    def handle_webhook_event(self, raw_payload: bytes, signature_header: Optional[str]) -> str:
        """Raises WebhookVerificationError (propagated from the provider)
        for a bad signature — the route must turn that into an HTTP 400,
        never a 200 (§9: this is a hard trust-boundary rejection, not a
        tool-specific outcome). Every other case returns a short outcome
        string and never raises, because Stripe interprets any non-2xx
        response as "redeliver this," and none of the "nothing to do"
        cases below (duplicate delivery, unmatched session, irrelevant
        event type, already-terminal payment) should trigger a retry
        loop."""
        event = self.provider.verify_and_parse_webhook(raw_payload, signature_header)

        # Idempotent event processing (§9) — reuses the SAME
        # IdempotencyStore create_payment_session already uses, keyed by
        # the provider's event id rather than inventing a second dedup
        # mechanism. Namespaced with a "stripe_event:" prefix so it can
        # never collide with the "idem_..."-prefixed keys
        # derive_idempotency_key() produces elsewhere in this codebase.
        dedup_key = f"stripe_event:{event.event_id}"
        if self.idempotency.begin(dedup_key) is not None:
            return "duplicate_event_ignored"

        try:
            if event.event_type not in RELEVANT_WEBHOOK_EVENT_TYPES:
                self.idempotency.complete(dedup_key, {"outcome": "ignored_irrelevant_type"})
                return "ignored_irrelevant_event_type"

            payment = (
                self.payments.get_by_provider_session_id(event.provider_session_id)
                if event.provider_session_id
                else None
            )
            if payment is None:
                # A real event for a session Charter123 has no record of
                # — e.g. a session created directly in the Stripe
                # Dashboard, or a stale/foreign webhook endpoint
                # misconfiguration. Logged, not errored: this endpoint
                # must not 500 just because Stripe sent something about a
                # session it doesn't recognize.
                record_audit_event(
                    self.db, actor="stripe_webhook", actor_type="system",
                    action="payment.webhook_unmatched_session", resource="payment",
                    resource_id=event.provider_session_id or "unknown",
                    metadata={"event_type": event.event_type, "event_id": event.event_id},
                )
                self.db.commit()
                self.idempotency.complete(dedup_key, {"outcome": "unmatched_session"})
                return "unmatched_session_ignored"

            new_status = new_status_for_webhook_event(event.event_type, event.payment_paid)
            if new_status is None or not can_transition(payment.status, new_status):
                # A no-op event type, or the payment already moved on
                # (e.g. a redelivered .completed arriving after we've
                # already processed the terminal async_payment_succeeded
                # for the same session) — accept quietly rather than
                # error; see method docstring on why this must stay a
                # non-raising path.
                self.idempotency.complete(dedup_key, {"outcome": "no_transition"})
                return "no_transition_needed"

            payment.status = new_status
            if event.payment_intent_id:
                payment.provider_payment_intent_id = event.payment_intent_id
            if new_status == "SUCCEEDED":
                payment.completed_at = datetime.now(timezone.utc)
            if new_status == "FAILED":
                payment.failure_code = event.failure_code or "payment_failed"
                payment.failure_message = event.failure_message or "The payment method could not be charged."

            booking = payment.booking
            booking.payment_status = BOOKING_PAYMENT_STATUS_FOR_SESSION[new_status]

            record_audit_event(
                self.db, actor="stripe_webhook", actor_type="system",
                action=f"payment.{new_status.lower()}", resource="payment", resource_id=str(payment.id),
                metadata={"pnr": booking.pnr, "event_type": event.event_type, "event_id": event.event_id},
            )
            self.db.commit()
            self.idempotency.complete(dedup_key, {"outcome": "transitioned", "new_status": new_status})
            return f"payment_{new_status.lower()}"
        except Exception:
            self.db.rollback()
            self.idempotency.fail(dedup_key)
            raise
