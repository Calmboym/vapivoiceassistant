from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.providers.airline.base import CabinClass


class FlightSearchRequest(BaseModel):
    origin: str = Field(..., min_length=3, max_length=3, description="IATA code, e.g. FRA")
    destination: str = Field(..., min_length=3, max_length=3)
    departure_date: date
    return_date: Optional[date] = None
    adults: int = Field(1, ge=1, le=20)
    children: int = Field(0, ge=0, le=20)
    infants: int = Field(0, ge=0, le=10)
    cabin_class: CabinClass = CabinClass.ECONOMY
    direct_only: bool = False

    @field_validator("origin", "destination")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class AircraftOut(BaseModel):
    id: str
    registration: str
    manufacturer: str
    model: str
    aircraft_type: str
    category: str
    seat_capacity: int
    available_seats: int
    range_km: int
    baggage_capacity_kg: int
    cabin_configuration: str
    amenities: list[str]
    status: str
    current_location: str


class FlightOfferOut(BaseModel):
    flight_id: str
    flight_number: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    aircraft: AircraftOut
    cabin_class: CabinClass
    available_seats: int
    price_per_passenger: Decimal
    currency: str
    direct: bool


class FareQuoteRequest(BaseModel):
    flight_id: str
    adults: int = Field(1, ge=1, le=20)
    children: int = Field(0, ge=0, le=20)
    infants: int = Field(0, ge=0, le=10)
    cabin_class: CabinClass = CabinClass.ECONOMY


class FareQuoteOut(BaseModel):
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


class AircraftAvailabilityRequest(BaseModel):
    origin: Optional[str] = None
    category: Optional[str] = Field(None, description="'commercial' or 'charter'")
    on_date: Optional[date] = None
    min_seats: Optional[int] = Field(None, ge=1)
