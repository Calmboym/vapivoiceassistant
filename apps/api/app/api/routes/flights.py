from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import get_airline_provider
from app.providers.airline.base import FlightNotFoundError
from app.schemas.common import ok
from app.schemas.flight import AircraftOut, FareQuoteOut, FareQuoteRequest, FlightOfferOut, FlightSearchRequest
from app.services.flight_service import FlightService

router = APIRouter(prefix="/api/v1/flights", tags=["flights"])


def _to_offer_out(offer) -> FlightOfferOut:
    return FlightOfferOut(
        flight_id=offer.flight_id, flight_number=offer.flight_number,
        origin=offer.origin, destination=offer.destination,
        departure_time=offer.departure_time, arrival_time=offer.arrival_time,
        duration_minutes=offer.duration_minutes,
        aircraft=AircraftOut(
            id=offer.aircraft.id, registration=offer.aircraft.registration,
            manufacturer=offer.aircraft.manufacturer, model=offer.aircraft.model,
            aircraft_type=offer.aircraft.aircraft_type, category=offer.aircraft.category,
            seat_capacity=offer.aircraft.seat_capacity, available_seats=offer.aircraft.available_seats,
            range_km=offer.aircraft.range_km, baggage_capacity_kg=offer.aircraft.baggage_capacity_kg,
            cabin_configuration=offer.aircraft.cabin_configuration, amenities=list(offer.aircraft.amenities),
            status=offer.aircraft.status, current_location=offer.aircraft.current_location,
        ),
        cabin_class=offer.cabin_class, available_seats=offer.available_seats,
        price_per_passenger=offer.price_per_passenger, currency=offer.currency, direct=offer.direct,
    )


@router.post("/search")
def search_flights(body: FlightSearchRequest, request: Request):
    service = FlightService(get_airline_provider())
    offers = service.search(
        origin=body.origin, destination=body.destination, departure_date=body.departure_date,
        adults=body.adults, children=body.children, infants=body.infants,
        cabin_class=body.cabin_class, direct_only=body.direct_only,
    )
    return ok([_to_offer_out(o) for o in offers], request.state.request_id)


@router.get("/{flight_id}")
def get_flight(flight_id: str, request: Request):
    service = FlightService(get_airline_provider())
    try:
        offer = service.get_flight(flight_id)
    except FlightNotFoundError:
        raise
    return ok(_to_offer_out(offer), request.state.request_id)


@router.post("/quote")
def get_fare_quote(body: FareQuoteRequest, request: Request):
    service = FlightService(get_airline_provider())
    quote = service.quote(
        flight_id=body.flight_id, adults=body.adults, children=body.children,
        infants=body.infants, cabin_class=body.cabin_class,
    )
    out = FareQuoteOut(
        quote_id=quote.quote_id, flight_id=quote.flight_id, adults=quote.adults,
        children=quote.children, infants=quote.infants, cabin_class=quote.cabin_class,
        base_fare=quote.base_fare, taxes=quote.taxes, fees=quote.fees,
        total_price=quote.total_price, currency=quote.currency, expires_at=quote.expires_at,
    )
    return ok(out, request.state.request_id)
