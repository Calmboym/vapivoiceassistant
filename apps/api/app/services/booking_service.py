from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailedError, VerificationFailedError
from app.core.idempotency import IdempotencyStore
from app.core.notifications.content import BaggageAllowance
from app.core.pnr import generate_unique_pnr
from app.models.booking import Booking, BookingPassenger
from app.providers.airline.base import AirlineProvider, CabinClass, PassengerInput, ProviderError
from app.repositories.booking_repository import BookingRepository
from app.repositories.customer_repository import CustomerRepository
from app.schemas.booking import BookingCreateRequest, BookingModifyRequest
from app.services.audit_service import record_audit_event
from app.services.notification_service import NotificationService
from app.services.verification_service import BookingVerificationService


class BookingService:
    def __init__(
        self,
        db: Session,
        provider: AirlineProvider,
        idempotency: IdempotencyStore,
        notifier: Optional[NotificationService] = None,
    ):
        self.db = db
        self.provider = provider
        self.idempotency = idempotency
        self.bookings = BookingRepository(db)
        self.customers = CustomerRepository(db)
        # T-5 (Phase 8): optional on purpose, default None — only the
        # create_booking() path below ever uses it. lookup/modify never
        # trigger a notification, so their call sites (three of the five
        # BookingService(...) constructions in app/api/routes/bookings.py
        # + app/api/routes/vapi.py) are deliberately left unchanged rather
        # than forced to thread a notifier they'd never use. A None
        # notifier simply means create_booking() skips the confirmation
        # side effect — the exact pre-T-5 behavior — never an error.
        self.notifier = notifier

    # ------------------------------------------------------------ create

    def create_booking(
        self, request: BookingCreateRequest, *, actor: str, call_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Booking:
        cached = self.idempotency.begin(request.idempotency_key)
        if cached is not None:
            if cached.status == "completed" and cached.result:
                existing = self.bookings.get_by_pnr(cached.result["pnr"])
                if existing:
                    return existing
            if cached.status == "in_progress":
                raise ValidationFailedError(
                    "BOOKING_IN_PROGRESS", "This booking request is already being processed."
                )

        try:
            provider_passengers = [
                PassengerInput(
                    first_name=p.first_name, last_name=p.last_name,
                    date_of_birth=p.date_of_birth, passenger_type=p.passenger_type,
                )
                for p in request.passengers
            ]
            provider_booking = self.provider.create_booking(
                quote_id=request.quote_id,
                passengers=provider_passengers,
                contact_email=request.contact.email,
                contact_phone=request.contact.phone,
                idempotency_key=request.idempotency_key,
            )

            customer = self.customers.get_or_create(request.contact.email, request.contact.phone)
            pnr = generate_unique_pnr(self.bookings.pnr_exists)

            # NOTE: AirlineProvider.create_booking() returns only a total —
            # not a base/tax/fee breakdown — because that's genuinely what
            # varies by provider (many real GDS order-creation responses DO
            # include a breakdown; MockAirlineProvider doesn't bother). We
            # record the true total and leave tax/fees at 0 rather than
            # inventing a split we don't actually have (§59: never invent
            # figures). A real adapter that gets a breakdown back should
            # populate these three fields properly.
            booking = Booking(
                pnr=pnr,
                provider_booking_reference=provider_booking.provider_booking_reference,
                provider_name="mock",
                status="CONFIRMED",
                payment_status="UNPAID",
                customer_id=customer.id,
                origin=provider_booking.origin,
                destination=provider_booking.destination,
                flight_number=provider_booking.flight_number,
                aircraft_type=provider_booking.aircraft_type,
                departure_time=provider_booking.departure_time,
                arrival_time=provider_booking.arrival_time,
                currency=provider_booking.currency,
                base_fare=provider_booking.total_price,
                tax=0,
                fees=0,
                total_price=provider_booking.total_price,
                contact_email=request.contact.email,
                contact_phone=request.contact.phone,
            )
            booking.passengers = [
                BookingPassenger(
                    provider_passenger_id=pp.passenger_id,
                    first_name=pp.first_name, last_name=pp.last_name,
                    date_of_birth=pp.date_of_birth, passenger_type=pp.passenger_type,
                )
                for pp in provider_booking.passengers
            ]
            self.bookings.add(booking)

            record_audit_event(
                self.db, actor=actor, actor_type="ai_agent" if call_id else "system",
                action="booking.created", resource="booking", resource_id=pnr,
                request_id=request_id, call_id=call_id,
                metadata={"provider_booking_reference": provider_booking.provider_booking_reference},
            )
            self.db.commit()

            self.idempotency.complete(request.idempotency_key, {"pnr": pnr})

            # T-5 (Phase 8, WBS-4.3): booking-confirmation notification —
            # a SYSTEM-triggered side effect on an already-committed,
            # already-true booking, never a step the mutation above
            # depends on. Runs AFTER commit()/idempotency.complete() so a
            # notification problem can never affect whether the booking
            # itself succeeded. self.notifier is None unless the caller
            # explicitly wired one in (see __init__ above) — most callers
            # (lookup/modify) never do, and that's fine, not an error.
            #
            # Broad except is deliberate defense-in-depth on top of
            # NotificationService's own internal try/except (see that
            # class's docstring) — this outer layer also catches a bug in
            # content-building itself (not just a provider failure),
            # which must equally never surface as a failed booking.
            if self.notifier is not None:
                try:
                    baggage = None
                    try:
                        rules = self.provider.get_baggage_rules(
                            CabinClass.ECONOMY, aircraft_type=booking.aircraft_type
                        )
                        baggage = BaggageAllowance(
                            checked_bags_included=rules.checked_bags_included,
                            checked_bag_max_kg=rules.checked_bag_max_kg,
                            cabin_bag_max_kg=rules.cabin_bag_max_kg,
                        )
                    except ProviderError:
                        # Honest omission, not a fabricated number — see
                        # app/core/notifications/content.py's docstring.
                        baggage = None
                    self.notifier.send_booking_confirmation(booking, baggage=baggage)
                except Exception:
                    pass

            return booking
        except Exception:
            self.db.rollback()
            self.idempotency.fail(request.idempotency_key)
            raise

    # ------------------------------------------------------------- lookup

    def get_verified_booking(
        self, pnr: str, *, email_or_phone: Optional[str] = None, last_name: Optional[str] = None
    ) -> Booking:
        booking = self.bookings.get_by_pnr(pnr)
        if booking is None:
            raise NotFoundError("BOOKING_NOT_FOUND", f"No booking found for PNR {pnr}.")
        if not BookingVerificationService.verify(booking, email_or_phone=email_or_phone, last_name=last_name):
            raise VerificationFailedError(
                "CUSTOMER_VERIFICATION_FAILED",
                "I couldn't verify your identity for this booking. Could you confirm the email, "
                "phone number, or last name on the reservation?",
            )
        return booking

    # ------------------------------------------------------------- modify

    def modify_booking(
        self, request: BookingModifyRequest, *, actor: str, call_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Booking:
        if not request.customer_confirmed:
            # Mirrors §16/§60: the backend never executes a change the
            # customer hasn't explicitly confirmed, no matter what the LLM
            # says happened in conversation.
            raise ValidationFailedError(
                "CONFIRMATION_REQUIRED", "This change requires explicit customer confirmation first."
            )

        booking = self.bookings.get_by_pnr(request.pnr)
        if booking is None:
            raise NotFoundError("BOOKING_NOT_FOUND", f"No booking found for PNR {request.pnr}.")
        if booking.status == "CANCELLED":
            raise ValidationFailedError("BOOKING_NOT_MODIFIABLE", "This booking has already been cancelled.")

        changes: dict = {}
        if request.new_flight_id:
            changes["new_flight_id"] = request.new_flight_id
        if request.new_contact_email:
            changes["contact_email"] = request.new_contact_email
        if request.new_contact_phone:
            changes["contact_phone"] = request.new_contact_phone
        if not changes:
            raise ValidationFailedError("NO_CHANGES_SPECIFIED", "No modification was specified.")

        try:
            updated = self.provider.update_booking(
                booking.provider_booking_reference, changes, request.idempotency_key
            )
            booking.status = "MODIFIED" if request.new_flight_id else booking.status
            booking.origin = updated.origin
            booking.destination = updated.destination
            booking.flight_number = updated.flight_number
            booking.aircraft_type = updated.aircraft_type
            booking.departure_time = updated.departure_time
            booking.arrival_time = updated.arrival_time
            booking.total_price = updated.total_price
            booking.contact_email = updated.contact_email
            booking.contact_phone = updated.contact_phone

            record_audit_event(
                self.db, actor=actor, actor_type="ai_agent" if call_id else "system",
                action="booking.modified", resource="booking", resource_id=booking.pnr,
                request_id=request_id, call_id=call_id, metadata={"changes": list(changes.keys())},
            )
            self.db.commit()
            return booking
        except Exception:
            self.db.rollback()
            raise
