from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PaymentSessionCreateRequest(BaseModel):
    """Deliberately has no `amount`/`currency` field at all — Milestone 1
    spec §6: "The amount must come from the authoritative Charter123
    booking/quote state. Never accept an arbitrary amount from Vapi [or
    the web client]." PaymentService always reads Booking.total_price/
    currency itself; there is nothing here for a forged/mistaken value to
    flow through."""

    pnr: str = Field(..., min_length=6, max_length=6)
    idempotency_key: str = Field(..., min_length=8, max_length=100)
    customer_confirmed: bool = Field(
        ...,
        description="Must be true — set only after the customer explicitly agreed to be charged the quoted total.",
    )
    # See BookingCancelRequest.verification_token in app/schemas/booking.py
    # — identical rule: an anonymous/voice caller must present a token
    # from a completed verify_booking_customer call; an authenticated
    # customer acting on their own booking, or staff, needs neither (see
    # app/api/deps_auth.py::require_payment_access, which never accepts
    # one at all — this field is only ever read by the Vapi dispatch
    # path's require_booking_access-equivalent check).
    verification_token: Optional[str] = None


class PaymentSessionOut(BaseModel):
    payment_id: str
    pnr: str
    status: str
    amount: Decimal
    currency: str
    # Structured data, not a claim that anyone has received it — see
    # docs/PAYMENTS.md "Known limitation: out-of-band delivery."
    checkout_url: Optional[str] = None
    expires_at: Optional[datetime] = None


class PaymentStatusOut(BaseModel):
    pnr: str
    booking_payment_status: str  # Booking.payment_status: UNPAID/PENDING/PAID/REFUNDED/FAILED
    latest_payment: Optional[PaymentSessionOut] = None
