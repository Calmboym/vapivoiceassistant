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


class RefundCreateRequest(BaseModel):
    """Staff/finance-only (PAYMENTS_REFUND — FINANCE/ADMIN/SUPER_ADMIN,
    see app/core/security/rbac.py). Never reachable via Vapi (T-3 — see
    docs/TASK_BOARD.md and tests.test_vapi_core.
    ToolRegistryConsistencyTests.
    test_authorization_entries_without_a_schema_are_exactly_staff_only).

    `amount` is optional (partial-refund override) rather than absent
    entirely like PaymentSessionCreateRequest's amount-less design: a
    refund's natural default (the full remaining amount) has to come
    from somewhere authoritative regardless, and PaymentService.
    refund_payment reads that default from Payment.amount/
    refunded_amount itself, never trusting `amount` beyond validating it
    doesn't exceed what's actually left on the payment — so this is NOT
    the same "amount from the caller" pattern §5 forbids for starting a
    NEW payment; it can only ever shrink what's returned, never invent
    or inflate a charge."""

    pnr: str = Field(..., min_length=6, max_length=6)
    idempotency_key: str = Field(..., min_length=8, max_length=100)
    confirmed: bool = Field(
        ...,
        description="Must be true — set only after staff has explicitly decided to issue this refund.",
    )
    amount: Optional[Decimal] = Field(
        None, gt=0, description="Partial refund amount. Omit for a full refund of whatever remains unrefunded."
    )
    reason: Optional[str] = Field(None, max_length=255)


class RefundOut(BaseModel):
    payment_id: str
    pnr: str
    payment_status: str  # Payment.status — always "SUCCEEDED"; see app/models/payment.py's refund-tracking comment
    booking_payment_status: str  # Booking.payment_status — "PAID" (partial) or "REFUNDED" (fully covered)
    refund_status: Optional[str] = None  # provider's raw Refund.status: pending/requires_action/succeeded/failed/canceled
    refunded_amount: Optional[Decimal] = None  # cumulative amount refunded so far on this Payment
    currency: str
    provider_refund_id: Optional[str] = None
