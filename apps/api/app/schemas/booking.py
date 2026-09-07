from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.passenger import ContactInfo, PassengerCreate, PassengerOut


class BookingCreateRequest(BaseModel):
    quote_id: str
    passengers: list[PassengerCreate] = Field(..., min_length=1, max_length=20)
    contact: ContactInfo
    # Set by the tool-call layer from trusted call context, never trusted
    # verbatim from the LLM's own free-form output — see docs/VAPI.md.
    idempotency_key: str = Field(..., min_length=8, max_length=100)


class BookingOut(BaseModel):
    pnr: str
    status: str
    payment_status: str
    origin: str
    destination: str
    flight_number: str
    aircraft_type: str
    departure_time: datetime
    arrival_time: datetime
    currency: str
    total_price: Decimal
    passengers: list[PassengerOut]
    cancellation_deadline: Optional[datetime] = None


class BookingLookupRequest(BaseModel):
    """Looking up a PNR alone is not authorization to act on it — see
    §13/BookingVerificationService in docs/BOOKING_FLOW.md. This schema is
    for *identity-verified* lookups only; the public/voice-facing route
    additionally requires one of email/phone/last_name to match."""

    pnr: str = Field(..., min_length=6, max_length=6)
    verification_email_or_phone: Optional[str] = None
    verification_last_name: Optional[str] = None


class BookingCancelRequest(BaseModel):
    pnr: str = Field(..., min_length=6, max_length=6)
    idempotency_key: str = Field(..., min_length=8, max_length=100)
    customer_confirmed: bool = Field(
        ..., description="Must be true — the tool layer sets this only after the customer said yes explicitly."
    )
    # Phase 4 (§11): customer_confirmed is a UX consent flag ("the
    # customer said yes to the fee"), never identity proof — it was
    # previously the ONLY gate on this endpoint, which is exactly the
    # gap §11 warns about ("A PNR alone must NOT authorize sensitive
    # mutations"). An anonymous/voice caller must now additionally
    # present a token from a completed POST /bookings/{pnr}/verify call;
    # an authenticated customer acting on their own booking, or staff,
    # needs neither — see app/api/deps_auth.py::require_booking_access.
    verification_token: Optional[str] = None


class CancellationQuoteOut(BaseModel):
    pnr: str
    refundable_amount: Decimal
    cancellation_fee: Decimal
    currency: str
    already_cancelled: bool


class BookingModifyRequest(BaseModel):
    pnr: str = Field(..., min_length=6, max_length=6)
    idempotency_key: str = Field(..., min_length=8, max_length=100)
    customer_confirmed: bool
    new_flight_id: Optional[str] = None
    new_contact_email: Optional[str] = None
    new_contact_phone: Optional[str] = None
    # See BookingCancelRequest.verification_token above — same rule.
    verification_token: Optional[str] = None


class BookingVerifyRequest(BaseModel):
    """§12: the controlled verification flow. `purpose` should match
    what the caller intends to do next (e.g. "cancel_booking") — a token
    verified for one purpose does not authorize a different one (see
    app.core.security.verification's scoped_to() check). If
    `verification_token` is omitted, a new verification session is
    started; if a caller is retrying after a wrong answer, pass the same
    token back so the attempt count keeps accumulating on ONE session
    instead of resetting for free on every retry."""

    pnr: str = Field(..., min_length=6, max_length=6)
    purpose: str = Field(..., min_length=1, max_length=50)
    verification_token: Optional[str] = None
    email_or_phone: Optional[str] = None
    last_name: Optional[str] = None


class BookingVerifyOut(BaseModel):
    status: str
    verification_token: str
    attempts: int
