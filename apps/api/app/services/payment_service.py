"""
PaymentService (Phase 6 Milestone 1; refund_payment added in T-3).

The ONE place payment business logic lives — app/api/routes/payments.py
(web) and app/api/routes/vapi.py's two new dispatch functions (voice)
both call the SAME methods on this class, exactly like BookingService/
CancellationService already do for the rest of the booking lifecycle
(see PROJECT_HANDOFF_PHASE_5's Milestone 1 spec §1/§11: "Do NOT implement
Vapi -> Stripe directly... The same Payment Service must be reusable by
the normal web/API layer."). refund_payment (T-3) is the one exception to
"both channels call the same methods" — it's STAFF_OR_ADMIN_ONLY and
never reachable via Vapi at all (see that method's own section docstring
and app/core/security/vapi_authorization.py), so only
app/api/routes/payments.py calls it; CancellationService calls this
class's apply_refund_outcome() helper directly instead, for reasons that
method's docstring explains.

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
from decimal import Decimal
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
from app.providers.payments.base import PaymentProvider, PaymentRefundError, RefundResult, RefundStatus
from app.repositories.booking_repository import BookingRepository
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import PaymentSessionCreateRequest, RefundCreateRequest
from app.services.audit_service import record_audit_event

# Refund.status values that mean the provider explicitly could NOT
# complete this refund (as opposed to PENDING/REQUIRES_ACTION, which
# just mean "not yet resolved" — see RefundResult's docstring).
_TERMINAL_FAILED_REFUND_STATUSES = frozenset({RefundStatus.FAILED, RefundStatus.CANCELED})


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

    # ------------------------------------------------------------- refund
    #
    # T-3 (docs/TASK_BOARD.md). Two entry points share the mutation logic
    # below (apply_refund_outcome) without sharing a commit/rollback
    # transaction boundary:
    #   - refund_payment(), just below: the staff-facing REST route's
    #     entry point (app/api/routes/payments.py POST /refunds). Owns
    #     its own full commit/rollback/idempotency-store transaction,
    #     exactly like create_payment_session above.
    #   - CancellationService.cancel(): calls apply_refund_outcome()
    #     directly (NOT this method) from inside its OWN try/except/
    #     commit block, because a cancellation's airline-side effect
    #     already happened and cannot be undone by rolling back this
    #     Session — see that module's comment for the full reasoning.
    #     Nesting two commit/rollback owners on the same shared
    #     SQLAlchemy Session would let a failed nested rollback erase the
    #     outer, already-true "booking was cancelled" state — this
    #     split is what avoids that, not an oversight.

    def apply_refund_outcome(
        self,
        *,
        payment: Payment,
        booking: Booking,
        provider_result: Optional[RefundResult],
        amount: Decimal,
        reason: Optional[str],
        mark_booking_refunded: bool,
        actor: str,
        call_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Payment:
        """Mutates `payment`/`booking` in place and writes ONE audit
        event. Does NOT call self.db.commit()/rollback() or touch the
        idempotency store — see the section docstring above for why that
        stays the caller's job.

        `provider_result=None` means "nothing was actually sent to the
        provider" — used only by CancellationService for the case where
        the airline's cancellation policy leaves nothing refundable (a
        cancellation fee absorbed the full amount). The Payment is still
        closed out honestly: refunded_amount=0, refund_status="succeeded"
        (trivially — there was nothing to fail), rather than pretending
        a Stripe call happened or silently doing nothing.

        `mark_booking_refunded` is the CALLER's decision, not this
        method's: CancellationService always passes True (a cancelled,
        previously-paid booking's payment lifecycle is closed out
        regardless of whether the refund was full or fee-adjusted — see
        that module). refund_payment() below passes True only once the
        CUMULATIVE refunded amount covers the full payment — a goodwill
        partial refund on an otherwise-active booking must not flip
        Booking.payment_status away from "PAID"."""
        payment.refund_reason = reason

        if provider_result is None:
            payment.refunded_amount = (payment.refunded_amount or Decimal("0")) + amount
            payment.refund_status = RefundStatus.SUCCEEDED.value
            payment.refunded_at = datetime.now(timezone.utc)
            audit_action = "payment.refunded"
            audit_metadata = {
                "pnr": booking.pnr, "amount": str(amount), "currency": payment.currency,
                "note": "cancellation fee absorbed the full amount; no provider refund was issued",
            }
        else:
            payment.provider_refund_id = provider_result.provider_refund_id
            payment.refunded_amount = (payment.refunded_amount or Decimal("0")) + provider_result.amount
            payment.refund_status = provider_result.status.value
            audit_metadata = {
                "pnr": booking.pnr, "amount": str(provider_result.amount), "currency": provider_result.currency,
                "provider_refund_id": provider_result.provider_refund_id, "status": provider_result.status.value,
            }
            if provider_result.status == RefundStatus.SUCCEEDED:
                payment.refunded_at = datetime.now(timezone.utc)
                audit_action = "payment.refunded"
            elif provider_result.status in _TERMINAL_FAILED_REFUND_STATUSES:
                audit_action = "payment.refund_failed"
            else:  # PENDING / REQUIRES_ACTION — not yet resolved, see class docstring
                audit_action = "payment.refund_pending"

        # Payment.status itself is deliberately never touched here — see
        # app/models/payment.py's refund-tracking comment.
        if mark_booking_refunded and (provider_result is None or provider_result.status == RefundStatus.SUCCEEDED):
            booking.payment_status = "REFUNDED"

        record_audit_event(
            self.db, actor=actor, actor_type="ai_agent" if call_id else "system",
            action=audit_action, resource="payment", resource_id=str(payment.id),
            request_id=request_id, call_id=call_id, metadata=audit_metadata,
        )
        return payment

    def refund_payment(self, request: RefundCreateRequest, *, actor: str) -> Payment:
        if not request.confirmed:
            raise ValidationFailedError(
                "CONFIRMATION_REQUIRED", "Refunding a payment requires explicit staff confirmation first."
            )

        booking = self.bookings.get_by_pnr(request.pnr)
        if booking is None:
            raise NotFoundError("BOOKING_NOT_FOUND", f"No booking found for PNR {request.pnr}.")
        if booking.payment_status == "REFUNDED":
            raise ConflictError("PAYMENT_ALREADY_REFUNDED", "This booking has already been refunded.")

        payment = self.payments.get_latest_for_booking(booking.id)
        if payment is None or payment.status != "SUCCEEDED" or not payment.provider_payment_intent_id:
            raise ValidationFailedError(
                "PAYMENT_NOT_REFUNDABLE", "This booking has no completed payment to refund."
            )

        already_refunded = payment.refunded_amount or Decimal("0")
        remaining = payment.amount - already_refunded
        refund_amount = request.amount if request.amount is not None else remaining
        if refund_amount <= 0 or refund_amount > remaining:
            raise ValidationFailedError(
                "INVALID_REFUND_AMOUNT",
                f"Refund amount must be greater than 0 and no more than {remaining} {payment.currency} remaining.",
            )

        cached = self.idempotency.begin(request.idempotency_key)
        if cached is not None:
            if cached.status == "completed" and cached.result:
                existing = self.payments.get_by_id(cached.result["payment_id"])
                if existing is not None:
                    return existing
            if cached.status == "in_progress":
                raise ValidationFailedError(
                    "REFUND_IN_PROGRESS", "This refund request is already being processed."
                )

        try:
            result = self.provider.refund_payment(
                payment_intent_id=payment.provider_payment_intent_id,
                amount=refund_amount,
                currency=payment.currency,
                idempotency_key=request.idempotency_key,
                reason=request.reason,
            )
        except Exception:
            # The provider call itself blew up (network/rejected before
            # any result existed) — nothing to commit, same pattern as
            # create_payment_session above.
            self.db.rollback()
            self.idempotency.fail(request.idempotency_key)
            raise

        will_complete_full_amount = (already_refunded + refund_amount) >= payment.amount
        self.apply_refund_outcome(
            payment=payment, booking=booking, provider_result=result, amount=refund_amount,
            reason=request.reason, mark_booking_refunded=will_complete_full_amount, actor=actor,
        )
        # Committed BEFORE any error is raised below — even a FAILED/
        # CANCELED provider response is a real fact worth keeping in the
        # audit trail and on the Payment row, not something a caught
        # exception should erase (§7: honest state, not a false "nothing
        # happened").
        self.db.commit()

        if result.status in _TERMINAL_FAILED_REFUND_STATUSES:
            self.idempotency.fail(request.idempotency_key)
            raise PaymentRefundError(f"The payment provider could not complete this refund (status: {result.status.value}).")

        self.idempotency.complete(request.idempotency_key, {"payment_id": str(payment.id)})
        return payment

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
