from __future__ import annotations

from app.core.exceptions import ValidationFailedError
from app.providers.airline.base import AirlineProvider, CabinClass, FareQuote, FlightOffer
from app.providers.airline.reference_data import AIRPORTS, resolve_city_or_iata


class AmbiguousAirportError(ValidationFailedError):
    """Raised when free text like 'London' matches more than one airport.
    Per §6: never silently guess when a booking could be affected — the
    caller (Vapi tool handler or web form) must ask the customer to
    disambiguate using `candidates`."""

    def __init__(self, text: str, candidates: tuple[str, ...]):
        self.candidates = candidates
        names = ", ".join(f"{c} ({AIRPORTS[c].name})" for c in candidates)
        super().__init__("AMBIGUOUS_AIRPORT", f"'{text}' matches multiple airports: {names}")


class FlightService:
    def __init__(self, provider: AirlineProvider):
        self.provider = provider

    def resolve_airport(self, text: str) -> str:
        """Resolves free text to a single IATA code, or raises
        AmbiguousAirportError if it maps to more than one (e.g. 'London')."""
        matches = resolve_city_or_iata(text)
        if not matches:
            raise ValidationFailedError("UNKNOWN_AIRPORT", f"I don't recognize '{text}' as an airport or city.")
        if len(matches) > 1:
            raise AmbiguousAirportError(text, matches)
        return matches[0]

    def search(
        self,
        origin: str,
        destination: str,
        departure_date,
        adults: int,
        children: int = 0,
        infants: int = 0,
        cabin_class: CabinClass = CabinClass.ECONOMY,
        direct_only: bool = False,
    ) -> list[FlightOffer]:
        return self.provider.search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            adults=adults,
            children=children,
            infants=infants,
            cabin_class=cabin_class,
            direct_only=direct_only,
        )

    def get_flight(self, flight_id: str) -> FlightOffer:
        return self.provider.get_flight(flight_id)

    def quote(
        self, flight_id: str, adults: int, children: int = 0, infants: int = 0,
        cabin_class: CabinClass = CabinClass.ECONOMY,
    ) -> FareQuote:
        return self.provider.get_fare_quote(
            flight_id, adults=adults, children=children, infants=infants, cabin_class=cabin_class
        )

    def aircraft_availability(self, **kwargs):
        return self.provider.get_aircraft_availability(**kwargs)

    def baggage_rules(self, cabin_class: CabinClass, aircraft_type: str | None = None):
        # Phase 5 addition: a thin passthrough, exactly matching the shape
        # of aircraft_availability() above. Added here (not called
        # directly from app/api/routes/vapi.py against the provider)
        # so the Vapi tool handler stays consistent with every other tool
        # — routes/tool-handlers call services, services call the
        # provider, never the reverse layering (§20 "Airline integrations
        # stay behind AirlineProvider").
        return self.provider.get_baggage_rules(cabin_class, aircraft_type=aircraft_type)
