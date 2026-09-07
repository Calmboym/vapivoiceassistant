from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Booking statuses, per §9. Stored as a plain indexed string (not a DB enum)
# so new statuses can be added via a simple migration rather than an
# ALTER TYPE — SQLite (used in dev/this sandbox) doesn't support enum
# alteration the way Postgres does.
BOOKING_STATUSES = (
    "QUOTE", "PENDING", "CONFIRMED", "TICKETED", "CHECKED_IN", "COMPLETED",
    "CANCEL_REQUESTED", "CANCELLED", "MODIFICATION_PENDING", "MODIFIED",
    "FAILED", "EXPIRED",
)
PAYMENT_STATUSES = ("UNPAID", "PENDING", "PAID", "REFUNDED", "FAILED")


class Booking(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bookings"

    pnr: Mapped[str] = mapped_column(String(6), unique=True, index=True, nullable=False)
    provider_booking_reference: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    provider_name: Mapped[str] = mapped_column(String(20), default="mock", nullable=False)

    status: Mapped[str] = mapped_column(String(30), default="QUOTE", nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), default="UNPAID", nullable=False)

    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id"), nullable=False)
    customer: Mapped["Customer"] = relationship(back_populates="bookings")

    # Itinerary snapshot — self-contained so booking status/lookup never
    # depends on the provider (mock or real) still remembering it, per §14.
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    flight_number: Mapped[str] = mapped_column(String(10), nullable=False)
    aircraft_type: Mapped[str] = mapped_column(String(20), nullable=False)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    base_fare: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    cancellation_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(32), nullable=False)

    passengers: Mapped[list["BookingPassenger"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Booking {self.pnr} {self.status}>"


class BookingPassenger(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "booking_passengers"

    booking_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("bookings.id"), nullable=False)
    booking: Mapped["Booking"] = relationship(back_populates="passengers")

    provider_passenger_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    passenger_type: Mapped[str] = mapped_column(String(10), default="adult", nullable=False)  # adult|child|infant
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Encrypted at rest — see app/core/encryption.py. Never store or log
    # the plaintext number; never speak it back in full (§10).
    passport_number_encrypted: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    passport_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    passport_expiry: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    frequent_flyer_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    meal_preference: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    seat_preference: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    special_assistance: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BookingPassenger {self.first_name} {self.last_name}>"
