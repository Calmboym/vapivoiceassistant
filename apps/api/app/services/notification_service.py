"""
NotificationService — the ONE place notification-dispatch logic lives
(T-5, docs/TASK_BOARD.md, Phase 8), mirroring PaymentService's own
framing of itself as "the ONE place payment business logic lives."
BookingService and PaymentService each depend on this class through
constructor injection — the exact pattern CancellationService already
established for PaymentService in T-3 — rather than importing
EmailProvider/SmsProvider directly, so neither service (nor a route, nor
a Vapi dispatch function) needs to know which channels exist, how
content is built, or how a delivery failure is recorded.

THIS IS A SYSTEM-TRIGGERED SIDE EFFECT, NEVER AN LLM-INVOKED ACTION —
MASTER_RULES.md §6: "Never give the Vapi assistant a tool for
send_confirmation/send_sms/send_email." This class has no Vapi tool
schema, no entry in TOOL_AUTHORIZATION_MATRIX, and is never called from
app/api/routes/vapi.py's dispatch table directly — it is called from
INSIDE BookingService.create_booking()/PaymentService.create_payment_
session(), the same layer a Vapi tool call eventually reaches but does
not itself choose to invoke, exactly like `transfer_to_human` logging an
escalation is a fact the backend records, not something the LLM
"performs" by naming a tool.

EVERY SEND HERE IS BEST-EFFORT AND NON-BLOCKING. This is a deliberate
design decision this session makes explicit: a failed confirmation
email/SMS must NEVER roll back or fail the booking/payment mutation that
already succeeded — the airline booked the seat, or Stripe created the
Checkout Session, regardless of whether Resend or Twilio can currently
be reached. Every public method here therefore:
  1. Catches its own provider's specific error type
     (EmailDeliveryError/SmsDeliveryError),
  2. Records an honest audit event either way (sent, or failed with the
     provider's own error code/message — never silently swallowed
     without a trace), and
  3. Never re-raises.
Callers (BookingService/PaymentService) additionally wrap the call site
itself in a broad try/except as defense-in-depth, in case a bug in
content-building (not a provider failure) would otherwise raise — see
those modules' own comments at the call site.

Content is built by the dependency-free functions in
app/core/notifications/content.py — this file's job is ONLY to convert
SQLAlchemy ORM objects into that module's plain dataclasses, call the
right builder, dispatch to the right provider method, and audit the
outcome. See that module's docstring for the content rules themselves
(never a passport number, never a fabricated cancellation fee/baggage
figure).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.notifications.content import (
    BaggageAllowance,
    BookingConfirmationData,
    PassengerSummary,
    PaymentLinkData,
    build_booking_confirmation_email,
    build_payment_link_email,
    build_payment_link_sms,
)
from app.models.booking import Booking
from app.models.payment import Payment
from app.services.audit_service import record_audit_event
from app.services.email_provider import EmailDeliveryError, EmailProvider
from app.services.sms_provider import SmsDeliveryError, SmsProvider


class NotificationService:
    def __init__(self, db: Session, email_provider: EmailProvider, sms_provider: SmsProvider):
        self.db = db
        self.email = email_provider
        self.sms = sms_provider

    # ------------------------------------------------------- booking confirmation

    def send_booking_confirmation(self, booking: Booking, *, baggage: BaggageAllowance | None) -> None:
        """Email only — see module docstring for why SMS isn't used
        here. `baggage` is computed by the CALLER (BookingService, which
        already holds an AirlineProvider) via get_baggage_rules(),
        deliberately defaulting to CabinClass.ECONOMY since Booking does
        not persist which cabin class was actually booked — pass None
        when that lookup wasn't possible/failed; this method never
        guesses a number itself. Never raises."""
        data = BookingConfirmationData(
            pnr=booking.pnr,
            origin=booking.origin,
            destination=booking.destination,
            flight_number=booking.flight_number,
            aircraft_type=booking.aircraft_type,
            departure_time=booking.departure_time,
            arrival_time=booking.arrival_time,
            currency=booking.currency,
            total_price=booking.total_price,
            payment_status=booking.payment_status,
            passengers=tuple(
                PassengerSummary(first_name=p.first_name, last_name=p.last_name, passenger_type=p.passenger_type)
                for p in booking.passengers
            ),
            cancellation_deadline=booking.cancellation_deadline,
            baggage=baggage,
        )
        content = build_booking_confirmation_email(data)
        idempotency_key = f"booking_confirmation/{booking.pnr}"
        try:
            self.email.send_booking_confirmation(
                to_email=booking.contact_email, pnr=booking.pnr, content=content, idempotency_key=idempotency_key,
            )
            self._audit(booking.pnr, "notification.booking_confirmation_sent", {"channel": "email"})
        except EmailDeliveryError as exc:
            self._audit(
                booking.pnr, "notification.booking_confirmation_failed",
                {"channel": "email", "error_code": exc.code, "error_message": exc.message},
            )

    # ------------------------------------------------------- payment link

    def send_payment_link(self, booking: Booking, payment: Payment, *, also_sms: bool) -> None:
        """Email always; SMS additionally when also_sms=True. See
        PaymentService.create_payment_session's call site for why that
        flag is `call_id is not None` (a live voice call) — the exact
        gap docs/PAYMENTS.md §8 documents: "a phone caller who needs the
        link delivered has no path to receive it today except a human
        transfer." Never raises."""
        data = PaymentLinkData(
            pnr=booking.pnr, amount=payment.amount, currency=payment.currency,
            checkout_url=payment.checkout_url, expires_at=payment.expires_at,
        )
        idempotency_key = f"payment_link/{payment.id}"

        content = build_payment_link_email(data)
        try:
            self.email.send_payment_link(
                to_email=booking.contact_email, pnr=booking.pnr, content=content, idempotency_key=idempotency_key,
            )
            self._audit(booking.pnr, "notification.payment_link_sent", {"channel": "email"})
        except EmailDeliveryError as exc:
            self._audit(
                booking.pnr, "notification.payment_link_failed",
                {"channel": "email", "error_code": exc.code, "error_message": exc.message},
            )

        if also_sms:
            sms_text = build_payment_link_sms(data)
            try:
                self.sms.send_payment_link(
                    to_phone=booking.contact_phone, pnr=booking.pnr, text_body=sms_text,
                    idempotency_key=idempotency_key,
                )
                self._audit(booking.pnr, "notification.payment_link_sent", {"channel": "sms"})
            except SmsDeliveryError as exc:
                self._audit(
                    booking.pnr, "notification.payment_link_failed",
                    {"channel": "sms", "error_code": exc.code, "error_message": exc.message},
                )

    # ------------------------------------------------------- internal

    def _audit(self, pnr: str, action: str, metadata: dict) -> None:
        # Own commit, separate from the caller's — same "log-then-
        # commit-separately" pattern already used by
        # PaymentService.handle_webhook_event's unmatched-session branch.
        # A failure writing THIS audit row must not raise either (it
        # would defeat the entire point of never blocking the caller) —
        # broad except here is deliberate, not sloppy.
        try:
            record_audit_event(
                self.db, actor="system", actor_type="system", action=action,
                resource="booking", resource_id=pnr, metadata=metadata,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
