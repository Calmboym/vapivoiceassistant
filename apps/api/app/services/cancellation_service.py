from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.idempotency import IdempotencyStore
from app.models.booking import Booking
from app.providers.airline.base import AirlineProvider, CancellationPolicy
from app.providers.payments.base import PaymentProvider, PaymentProviderError
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import BookingCancelRequest
from app.services.audit_service import record_audit_event
from app.services.payment_service import PaymentService


class CancellationService:
    def __init__(
        self, db: Session, provider: AirlineProvider, idempotency: IdempotencyStore, payment_provider: PaymentProvider
    ):
        self.db = db
        self.provider = provider
        self.idempotency = idempotency
        self.bookings = BookingRepository(db)
        # T-3: used directly (not via PaymentService.refund_payment, which
        # owns its own commit/rollback) — see cancel()'s comment on why
        # two commit/rollback owners must not nest on one shared Session.
        # PaymentService is still reused here for its apply_refund_outcome
        # helper and its PaymentRepository, so the "translate a
        # RefundResult into Payment/Booking fields + one audit event"
        # logic lives in exactly one place.
        self.payment_provider = payment_provider
        self.payment_service = PaymentService(db, payment_provider, idempotency)

    def get_policy(self, pnr: str) -> tuple[Booking, CancellationPolicy]:
        booking = self.bookings.get_by_pnr(pnr)
        if booking is None:
            raise NotFoundError("BOOKING_NOT_FOUND", f"No booking found for PNR {pnr}.")
        if booking.status == "CANCELLED":
            return booking, CancellationPolicy(
                provider_booking_reference=booking.provider_booking_reference or "",
                refundable_amount=0, cancellation_fee=0, non_refundable_amount=0,
                currency=booking.currency, deadline=booking.updated_at, already_cancelled=True,
            )
        policy = self.provider.get_cancellation_policy(booking.provider_booking_reference)
        return booking, policy

    def cancel(
        self, request: BookingCancelRequest, *, actor: str, call_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> tuple[Booking, bool]:
        """Returns (booking, already_was_cancelled). Cancellation is
        idempotent (§15): cancelling an already-cancelled booking is a
        no-op that succeeds rather than erroring."""
        if not request.customer_confirmed:
            raise ValidationFailedError(
                "CONFIRMATION_REQUIRED", "Cancellation requires explicit customer confirmation first."
            )

        booking = self.bookings.get_by_pnr(request.pnr)
        if booking is None:
            raise NotFoundError("BOOKING_NOT_FOUND", f"No booking found for PNR {request.pnr}.")

        if booking.status == "CANCELLED":
            return booking, True

        cached = self.idempotency.begin(request.idempotency_key)
        if cached is not None and cached.status == "completed":
            return booking, False

        try:
            result = self.provider.cancel_booking(booking.provider_booking_reference, request.idempotency_key)
            booking.status = "CANCELLED"

            # T-3 (docs/TASK_BOARD.md): the airline cancellation above
            # already happened and is irreversible from here — nothing
            # below may raise in a way that unwinds it. A previously-PAID
            # booking gets refunded for real now, using the airline's own
            # refundable_amount (net of cancellation_fee, not
            # Payment.amount outright — a cancellation fee is real money
            # the airline keeps).
            if booking.payment_status == "PAID":
                payment = self.payment_service.payments.get_latest_for_booking(booking.id)
                if payment is not None and payment.status == "SUCCEEDED" and payment.provider_payment_intent_id:
                    already_refunded = payment.refunded_amount or Decimal("0")
                    remaining = payment.amount - already_refunded
                    refund_amount = result.refundable_amount
                    if refund_amount > remaining:
                        refund_amount = remaining  # never ask the provider to refund more than is left
                    if refund_amount <= 0:
                        # Fully absorbed by the cancellation fee — nothing
                        # to send Stripe. Still close out the Payment
                        # honestly (refunded_amount=0) rather than
                        # skipping this branch entirely.
                        self.payment_service.apply_refund_outcome(
                            payment=payment, booking=booking, provider_result=None, amount=Decimal("0"),
                            reason="booking_cancelled", mark_booking_refunded=True, actor=actor,
                            call_id=call_id, request_id=request_id,
                        )
                    else:
                        try:
                            provider_result = self.payment_provider.refund_payment(
                                payment_intent_id=payment.provider_payment_intent_id,
                                amount=refund_amount,
                                currency=payment.currency,
                                # Deterministic and tied 1:1 to this
                                # cancellation's own idempotency_key — a
                                # retried cancel request must not trigger
                                # a second Stripe refund.
                                idempotency_key=f"refund_for_cancel:{request.idempotency_key}",
                                reason="booking_cancelled",
                            )
                            self.payment_service.apply_refund_outcome(
                                payment=payment, booking=booking, provider_result=provider_result,
                                amount=refund_amount, reason="booking_cancelled", mark_booking_refunded=True,
                                actor=actor, call_id=call_id, request_id=request_id,
                            )
                        except PaymentProviderError as exc:
                            # The airline cancellation already happened
                            # and can't be undone by rolling back this
                            # transaction, so this is caught here (not
                            # re-raised) rather than aborting the whole
                            # cancel() call. booking.payment_status is
                            # deliberately left "PAID" — never falsely
                            # "REFUNDED" — so this stays visible. The
                            # staff-only refund_payment REST route (T-3,
                            # same milestone) is the manual recovery path
                            # for exactly this case.
                            record_audit_event(
                                self.db, actor=actor, actor_type="ai_agent" if call_id else "system",
                                action="payment.refund_failed_during_cancellation", resource="payment",
                                resource_id=str(payment.id), request_id=request_id, call_id=call_id,
                                metadata={"pnr": booking.pnr, "error": getattr(exc, "message", str(exc))},
                            )
                # else: payment_status says PAID but no SUCCEEDED payment
                # row with a provider_payment_intent_id was found — data
                # drift, not this method's job to guess at; payment_status
                # is left untouched rather than assumed.

            record_audit_event(
                self.db, actor=actor, actor_type="ai_agent" if call_id else "system",
                action="booking.cancelled", resource="booking", resource_id=booking.pnr,
                request_id=request_id, call_id=call_id,
                metadata={
                    "refundable_amount": str(result.refundable_amount),
                    "cancellation_fee": str(result.cancellation_fee),
                },
            )
            self.db.commit()
            self.idempotency.complete(request.idempotency_key, {"pnr": booking.pnr})
            return booking, False
        except Exception:
            self.db.rollback()
            self.idempotency.fail(request.idempotency_key)
            raise

