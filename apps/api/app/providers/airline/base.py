"""
AirlineProvider — the provider-agnostic contract for airline/GDS integration.

Every backend service (flight search, booking, cancellation, etc.) talks to
*this* interface only. It never imports MockAirlineProvider, AmadeusAirlineProvider,
or SabreAirlineProvider directly outside of app/core/config.py's provider factory.
That is what lets AIRLINE_PROVIDER=mock become AIRLINE_PROVIDER=amadeus later
without touching a single service or route.

Deliberately dependency-free (stdlib only: abc, dataclasses, datetime, decimal,
enum, typing) so this file — and any provider built against it — can be
imported and unit-tested without FastAPI/SQLAlchemy/a database being present.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol


class CabinClass(str, Enum):
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"
    CHARTER = "charter"


class ProviderBookingStatus(str, Enum):
    HELD = "held"
    CONFIRMED = "confirmed"
    TICKETED = "ticketed"
    CANCELLED = "cancelled"
    MODIFIED = "modified"
    FAILED = "failed"


@dataclass(frozen=True)
class Airport:
    iata: str
    icao: str
    name: str
    city: str
    country: str
    timezone: str  # IANA tz name, e.g. "Europe/Berlin"
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Aircraft:
    id: str
    registration: str
    manufacturer: str
    model: str
    aircraft_type: str
    category: str  # "commercial" | "charter"
    seat_capacity: int
    available_seats: int
    range_km: int
    baggage_capacity_kg: int
    cabin_configuration: str
    amenities: tuple[str, ...]
    status: str  # "available" | "in_service" | "maintenance"
    current_location: str  # IATA code
    next_available_at: Optional[datetime]


@dataclass(frozen=True)
class FlightOffer:
    """A single bookable option returned from search_flights / get_flight."""
    flight_id: str
    flight_number: str
    origin: str
    destination: str
    departure_time: datetime  # tz-aware, local to origin airport
    arrival_time: datetime    # tz-aware, local to destination airport
    duration_minutes: int
    aircraft: Aircraft
    cabin_class: CabinClass
    available_seats: int
    price_per_passenger: Decimal
    currency: str
    direct: bool
    stops: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FareQuote:
    quote_id: str
    flight_id: str
    adults: int
    children: int
    infants: int
    cabin_class: CabinClass
    base_fare: Decimal
    taxes: Decimal
    fees: Decimal
    total_price: Decimal
    currency: str
    expires_at: datetime


@dataclass
class PassengerInput:
    """Minimal passenger data the provider needs — NOT the full passport record."""
    first_name: str
    last_name: str
    date_of_birth: Optional[date] = None
    passenger_type: str = "adult"  # adult | child | infant
    passenger_id: Optional[str] = None  # set by provider on creation


@dataclass
class ProviderBooking:
    provider_booking_reference: str
    status: ProviderBookingStatus
    flight_id: str
    flight_number: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    aircraft_type: str
    passengers: list[PassengerInput]
    contact_email: str
    contact_phone: str
    total_price: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CancellationPolicy:
    provider_booking_reference: str
    refundable_amount: Decimal
    cancellation_fee: Decimal
    non_refundable_amount: Decimal
    currency: str
    deadline: datetime  # last moment this quote is valid
    already_cancelled: bool = False


@dataclass(frozen=True)
class CancellationResult:
    provider_booking_reference: str
    status: ProviderBookingStatus
    refundable_amount: Decimal
    cancellation_fee: Decimal
    currency: str
    already_cancelled: bool


@dataclass(frozen=True)
class BaggageRules:
    cabin_class: CabinClass
    checked_bags_included: int
    checked_bag_max_kg: int
    cabin_bag_max_kg: int
    extra_bag_fee: Decimal
    currency: str
    notes: str


@dataclass(frozen=True)
class FareRules:
    flight_id: str
    cabin_class: CabinClass
    refundable: bool
    changeable: bool
    change_fee: Decimal
    currency: str
    notes: str


class ProviderError(Exception):
    """Base class for provider-side failures. Services must catch this and
    translate it into a structured, user-safe error — never a raw exception
    or backend stack trace spoken/shown to a customer."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


class FlightNotFoundError(ProviderError):
    def __init__(self, flight_id: str):
        super().__init__("FLIGHT_NOT_FOUND", f"No such flight: {flight_id}", retryable=False)


class BookingNotFoundError(ProviderError):
    def __init__(self, reference: str):
        super().__init__("BOOKING_NOT_FOUND", f"No such booking: {reference}", retryable=False)


class ProviderUnavailableError(ProviderError):
    def __init__(self, detail: str = "provider temporarily unavailable"):
        super().__init__("PROVIDER_UNAVAILABLE", detail, retryable=True)


@dataclass(frozen=True)
class ProviderCapabilities:
    """Lets the application adapt to what a given provider can actually do,
    per MASTER BUILD PROMPT §69. MockAirlineProvider supports everything;
    a real adapter may not."""
    supports_hold_booking: bool
    supports_payment: bool
    supports_cancellation: bool
    supports_modification: bool
    supports_seat_selection: bool
    supports_baggage: bool
    supports_charter: bool
    supports_passenger_updates: bool


class AirlineProvider(ABC):
    """Provider-agnostic airline/GDS interface. Implement this once per
    backend (mock, Amadeus, Sabre, ...) and nothing above this layer changes."""

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        adults: int,
        children: int = 0,
        infants: int = 0,
        cabin_class: CabinClass = CabinClass.ECONOMY,
        return_date: Optional[date] = None,
        direct_only: bool = False,
        max_results: int = 6,
    ) -> list[FlightOffer]: ...

    @abstractmethod
    def get_flight(self, flight_id: str) -> FlightOffer: ...

    @abstractmethod
    def get_aircraft_availability(
        self,
        origin: Optional[str] = None,
        category: Optional[str] = None,
        on_date: Optional[date] = None,
        min_seats: Optional[int] = None,
    ) -> list[Aircraft]: ...

    @abstractmethod
    def get_fare_quote(
        self,
        flight_id: str,
        adults: int,
        children: int = 0,
        infants: int = 0,
        cabin_class: CabinClass = CabinClass.ECONOMY,
    ) -> FareQuote: ...

    @abstractmethod
    def create_booking(
        self,
        quote_id: str,
        passengers: list[PassengerInput],
        contact_email: str,
        contact_phone: str,
        idempotency_key: str,
    ) -> ProviderBooking: ...

    @abstractmethod
    def get_booking(self, provider_booking_reference: str) -> ProviderBooking: ...

    @abstractmethod
    def update_booking(
        self,
        provider_booking_reference: str,
        changes: dict,
        idempotency_key: str,
    ) -> ProviderBooking: ...

    @abstractmethod
    def cancel_booking(
        self, provider_booking_reference: str, idempotency_key: str
    ) -> CancellationResult: ...

    @abstractmethod
    def get_cancellation_policy(self, provider_booking_reference: str) -> CancellationPolicy: ...

    @abstractmethod
    def add_passenger(
        self, provider_booking_reference: str, passenger: PassengerInput
    ) -> ProviderBooking: ...

    @abstractmethod
    def remove_passenger(
        self, provider_booking_reference: str, passenger_id: str
    ) -> ProviderBooking: ...

    @abstractmethod
    def get_booking_status(self, provider_booking_reference: str) -> ProviderBookingStatus: ...

    @abstractmethod
    def get_baggage_rules(
        self, cabin_class: CabinClass, aircraft_type: Optional[str] = None
    ) -> BaggageRules: ...

    @abstractmethod
    def get_fare_rules(self, flight_id: str, cabin_class: CabinClass) -> FareRules: ...
