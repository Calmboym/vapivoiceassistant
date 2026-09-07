from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Query, Request

from app.api.deps import get_airline_provider
from app.schemas.common import ok
from app.schemas.flight import AircraftOut
from app.services.flight_service import FlightService

router = APIRouter(prefix="/api/v1/aircraft", tags=["aircraft"])


@router.get("/availability")
def get_aircraft_availability(
    request: Request,
    origin: Optional[str] = Query(None, min_length=3, max_length=3),
    category: Optional[str] = Query(None, pattern="^(commercial|charter)$"),
    on_date: Optional[date_type] = None,
    min_seats: Optional[int] = Query(None, ge=1),
):
    service = FlightService(get_airline_provider())
    aircraft = service.aircraft_availability(
        origin=origin.upper() if origin else None, category=category, on_date=on_date, min_seats=min_seats,
    )
    out = [
        AircraftOut(
            id=a.id, registration=a.registration, manufacturer=a.manufacturer, model=a.model,
            aircraft_type=a.aircraft_type, category=a.category, seat_capacity=a.seat_capacity,
            available_seats=a.available_seats, range_km=a.range_km, baggage_capacity_kg=a.baggage_capacity_kg,
            cabin_configuration=a.cabin_configuration, amenities=list(a.amenities), status=a.status,
            current_location=a.current_location,
        )
        for a in aircraft
    ]
    return ok(out, request.state.request_id)
