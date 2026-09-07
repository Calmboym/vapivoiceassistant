from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.encryption import encrypt_sensitive
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.models.booking import Booking, BookingPassenger
from app.providers.airline.base import AirlineProvider, PassengerInput
from app.repositories.booking_repository import BookingRepository
from app.schemas.passenger import PassengerCreate, PassportDetails
from app.services.audit_service import record_audit_event


class PassengerService:
    def __init__(self, db: Session, provider: AirlineProvider):
        self.db = db
        self.provider = provider
        self.bookings = BookingRepository(db)

    def add_passenger(
        self, pnr: str, passenger: PassengerCreate, *, actor: str, call_id: Optional[str] = None
    ) -> Booking:
        booking = self._get_active_booking(pnr)
        provider_input = PassengerInput(
            first_name=passenger.first_name, last_name=passenger.last_name,
            date_of_birth=passenger.date_of_birth, passenger_type=passenger.passenger_type,
        )
        updated = self.provider.add_passenger(booking.provider_booking_reference, provider_input)

        booking.passengers.append(
            BookingPassenger(
                provider_passenger_id=provider_input.passenger_id,
                first_name=passenger.first_name, middle_name=passenger.middle_name,
                last_name=passenger.last_name, date_of_birth=passenger.date_of_birth,
                passenger_type=passenger.passenger_type, gender=passenger.gender,
                nationality=passenger.nationality, meal_preference=passenger.meal_preference,
                seat_preference=passenger.seat_preference, special_assistance=passenger.special_assistance,
                frequent_flyer_number=passenger.frequent_flyer_number,
            )
        )
        booking.total_price = updated.total_price

        record_audit_event(
            self.db, actor=actor, actor_type="ai_agent" if call_id else "system",
            action="passenger.added", resource="booking", resource_id=pnr, call_id=call_id,
        )
        self.db.commit()
        return booking

    def remove_passenger(
        self, pnr: str, booking_passenger_id: str, *, actor: str, call_id: Optional[str] = None
    ) -> Booking:
        booking = self._get_active_booking(pnr)
        target = next((p for p in booking.passengers if str(p.id) == booking_passenger_id), None)
        if target is None:
            raise NotFoundError("PASSENGER_NOT_FOUND", "No such passenger on this booking.")
        if len(booking.passengers) <= 1:
            raise ValidationFailedError("PASSENGER_VALIDATION_FAILED", "A booking must have at least one passenger.")

        if target.provider_passenger_id:
            updated = self.provider.remove_passenger(booking.provider_booking_reference, target.provider_passenger_id)
            booking.total_price = updated.total_price
        booking.passengers.remove(target)

        record_audit_event(
            self.db, actor=actor, actor_type="ai_agent" if call_id else "system",
            action="passenger.removed", resource="booking", resource_id=pnr, call_id=call_id,
        )
        self.db.commit()
        return booking

    def add_passport_details(
        self, pnr: str, booking_passenger_id: str, passport: PassportDetails, *, actor: str,
        call_id: Optional[str] = None,
    ) -> Booking:
        """Deliberately a separate call from add_passenger (§10: don't ask
        for passport info until it's actually needed). The passport number
        is encrypted before it ever touches the database."""
        booking = self._get_active_booking(pnr)
        target = next((p for p in booking.passengers if str(p.id) == booking_passenger_id), None)
        if target is None:
            raise NotFoundError("PASSENGER_NOT_FOUND", "No such passenger on this booking.")

        target.passport_number_encrypted = encrypt_sensitive(passport.passport_number)
        target.passport_country = passport.passport_country
        target.passport_expiry = passport.passport_expiry

        # Never write the plaintext passport number into the audit trail.
        record_audit_event(
            self.db, actor=actor, actor_type="ai_agent" if call_id else "system",
            action="passenger.passport_updated", resource="booking", resource_id=pnr, call_id=call_id,
        )
        self.db.commit()
        return booking

    def _get_active_booking(self, pnr: str) -> Booking:
        booking = self.bookings.get_by_pnr(pnr)
        if booking is None:
            raise NotFoundError("BOOKING_NOT_FOUND", f"No booking found for PNR {pnr}.")
        if booking.status == "CANCELLED":
            raise ValidationFailedError("BOOKING_NOT_MODIFIABLE", "This booking has already been cancelled.")
        return booking
