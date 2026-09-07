"""
Placeholder for a real Amadeus Self-Service / Enterprise API integration.

Per MASTER BUILD PROMPT §5/§40: "Do not invent undocumented third-party
APIs" and "Do not fabricate API URLs." No Amadeus credentials or API
documentation were available when this codebase was generated, so this
adapter deliberately does NOT call any Amadeus endpoint — every method
raises NotImplementedError with a pointer to what's needed.

To implement this for real:
  1. Get Amadeus for Developers credentials (or Enterprise credentials).
  2. Set AIRLINE_PROVIDER=amadeus, AIRLINE_API_BASE_URL, AIRLINE_API_KEY,
     AIRLINE_API_SECRET in the environment.
  3. Implement each method below against Amadeus's actual documented
     endpoints (e.g. Flight Offers Search, Flight Create Orders) —
     translating their response shapes into the same dataclasses
     MockAirlineProvider returns, so nothing above this layer changes.
  4. Translate Amadeus error responses into the ProviderError subclasses
     in app/providers/airline/base.py so app/core/exceptions.py's handling
     keeps working unmodified.
"""

from __future__ import annotations

from datetime import date

from app.core.config import get_settings
from app.providers.airline.base import (
    AirlineProvider,
    Aircraft,
    BaggageRules,
    CabinClass,
    CancellationPolicy,
    CancellationResult,
    FareQuote,
    FareRules,
    FlightOffer,
    PassengerInput,
    ProviderBooking,
    ProviderBookingStatus,
    ProviderCapabilities,
)

_NOT_IMPLEMENTED = (
    "AmadeusAirlineProvider is a placeholder — no Amadeus credentials or API "
    "documentation were available at build time. See this file's module "
    "docstring and docs/AIRLINE_PROVIDER.md for what's needed to implement it."
)


class AmadeusAirlineProvider(AirlineProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.airline_api_base_url or not settings.airline_api_key:
            raise RuntimeError(
                "AIRLINE_PROVIDER=amadeus but AIRLINE_API_BASE_URL/AIRLINE_API_KEY "
                "are not set. " + _NOT_IMPLEMENTED
            )
        # Real implementation would build an httpx client / OAuth2 token
        # manager here using settings.airline_api_key / _secret.
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def search_flights(self, origin: str, destination: str, departure_date: date, adults: int, **kwargs) -> list[FlightOffer]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_flight(self, flight_id: str) -> FlightOffer:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_aircraft_availability(self, **kwargs) -> list[Aircraft]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_fare_quote(self, flight_id: str, adults: int, **kwargs) -> FareQuote:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def create_booking(self, quote_id: str, passengers: list[PassengerInput], contact_email: str, contact_phone: str, idempotency_key: str) -> ProviderBooking:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_booking(self, provider_booking_reference: str) -> ProviderBooking:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def update_booking(self, provider_booking_reference: str, changes: dict, idempotency_key: str) -> ProviderBooking:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def cancel_booking(self, provider_booking_reference: str, idempotency_key: str) -> CancellationResult:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_cancellation_policy(self, provider_booking_reference: str) -> CancellationPolicy:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def add_passenger(self, provider_booking_reference: str, passenger: PassengerInput) -> ProviderBooking:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def remove_passenger(self, provider_booking_reference: str, passenger_id: str) -> ProviderBooking:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_booking_status(self, provider_booking_reference: str) -> ProviderBookingStatus:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_baggage_rules(self, cabin_class: CabinClass, aircraft_type: str | None = None) -> BaggageRules:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_fare_rules(self, flight_id: str, cabin_class: CabinClass) -> FareRules:
        raise NotImplementedError(_NOT_IMPLEMENTED)
