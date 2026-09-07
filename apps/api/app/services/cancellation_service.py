from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.idempotency import IdempotencyStore
from app.models.booking import Booking
from app.providers.airline.base import AirlineProvider, CancellationPolicy
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import BookingCancelRequest
from app.services.audit_service import record_audit_event


class CancellationService:
    def __init__(self, db: Session, provider: AirlineProvider, idempotency: IdempotencyStore):
        self.db = db
        self.provider = provider
        self.idempotency = idempotency
        self.bookings = BookingRepository(db)

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
            # KNOWN LIMITATION (pre-existing since before Phase 6 Milestone
            # 1, now load-bearing rather than dead code): this flips the
            # LOCAL payment_status field only — it does NOT call Stripe
            # (or any PaymentProvider) to actually refund anything. Before
            # Milestone 1, booking.payment_status could never actually
            # reach "PAID" (nothing set it), so this line was unreachable
            # in practice. It is reachable now. A cancelled, previously-
            # paid booking will report "REFUNDED" here without a real
            # refund having occurred — see docs/PAYMENTS.md "Known
            # limitations" and the STAFF_OR_ADMIN_ONLY `refund_payment`
            # tool already reserved (but not implemented) in
            # app/core/security/vapi_authorization.py. Deliberately NOT
            # fixed in this milestone (out of its stated scope:
            # create_payment_session + get_payment_status only) — flagged
            # here so it isn't mistaken for a false financial state that
            # was overlooked rather than one that's tracked.
            booking.payment_status = "REFUNDED" if booking.payment_status == "PAID" else booking.payment_status

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
