from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class PassengerCreate(BaseModel):
    """Minimal passenger data needed to BOOK. Passport/visa details are
    deliberately a separate, later step (§10: don't ask for passport
    information until it's actually needed)."""

    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: Optional[date] = None
    passenger_type: str = Field("adult", pattern="^(adult|child|infant)$")
    gender: Optional[str] = Field(None, max_length=20)
    nationality: Optional[str] = Field(None, max_length=100)
    meal_preference: Optional[str] = Field(None, max_length=50)
    seat_preference: Optional[str] = Field(None, max_length=50)
    special_assistance: Optional[str] = Field(None, max_length=255)
    frequent_flyer_number: Optional[str] = Field(None, max_length=50)
    # Phase 4 (§10/§11): an anonymous/voice caller adding or changing a
    # passenger must present a token from a completed
    # POST /bookings/{pnr}/verify call, same rule as booking cancel/
    # modify — passenger records inherit their booking's ownership. An
    # authenticated owner or staff member needs neither.
    verification_token: Optional[str] = None


class PassportDetails(BaseModel):
    """Collected separately (e.g. right before ticketing), and never
    echoed back in full — see app.core.encryption.mask_for_speech."""

    passport_number: str = Field(..., min_length=5, max_length=20)
    passport_country: str = Field(..., max_length=100)
    passport_expiry: date
    verification_token: Optional[str] = None


class PassengerOut(BaseModel):
    id: str
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    passenger_type: str
    meal_preference: Optional[str] = None
    seat_preference: Optional[str] = None
    special_assistance: Optional[str] = None
    frequent_flyer_number: Optional[str] = None
    passport_on_file: bool = False
    passport_number_masked: Optional[str] = None


class ContactInfo(BaseModel):
    email: EmailStr
    phone: str = Field(..., min_length=6, max_length=32)
