from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.booking import BookingOut
from app.schemas.common import PageMeta


class AdminBookingOut(BookingOut):
    """BookingOut plus the internal identifiers a STAFF list/detail view
    needs (to link to a detail page, and to filter/group by customer)
    that the customer-facing BookingOut deliberately omits — a customer
    already knows their own PNR and has no need to see their own
    internal UUID; staff browsing bookings across every customer does.
    Extends rather than modifies BookingOut so none of its three
    existing customer-facing callers (create_booking, lookup_booking,
    list_my_bookings — all in app/api/routes/bookings.py) change at
    all."""

    id: str
    customer_id: str
    customer_email: Optional[str] = None


class AdminBookingListOut(BaseModel):
    items: list[AdminBookingOut]
    page: PageMeta


class PaymentSummaryOut(BaseModel):
    """Staff-facing payment view. Deliberately NOT the same shape as any
    customer-facing payment response (there isn't one today — Phase 6/7
    never added a customer GET for their own payment history) — this is
    new, staff-only surface, so it can safely include provider
    identifiers (provider_payment_intent_id etc.) that would be
    unnecessary detail for a customer, without that being a behavior
    CHANGE to anything pre-existing."""

    id: str
    status: str
    amount: Decimal
    currency: str
    provider_name: str
    provider_payment_intent_id: Optional[str] = None
    refunded_amount: Optional[Decimal] = None
    refund_status: Optional[str] = None
    refund_reason: Optional[str] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class AuditLogEntryOut(BaseModel):
    id: str
    actor: str
    actor_type: str
    action: str
    resource: str
    resource_id: Optional[str] = None
    call_id: Optional[str] = None
    event_metadata: Optional[dict] = None
    created_at: datetime


class AdminBookingDetailOut(BaseModel):
    """A booking's full staff-facing picture: the booking itself, every
    payment attempt against it (not just the latest — see
    PaymentRepository.list_for_booking's own docstring on why a
    FAILED/EXPIRED attempt followed by a later SUCCEEDED one are BOTH
    kept), and its complete audit trail (WBS-5's exit criterion: "see a
    booking's full audit trail")."""

    booking: AdminBookingOut
    payments: list[PaymentSummaryOut] = Field(default_factory=list)
    audit_trail: list[AuditLogEntryOut] = Field(default_factory=list)


class DailyRevenuePointOut(BaseModel):
    day: str
    currency: str
    net_amount: Decimal


class AnalyticsSummaryOut(BaseModel):
    """Mirrors app.core.admin.analytics.AnalyticsSummary field-for-field
    — see that module's docstring for the honesty note on why this does
    NOT include a "quote conversion rate" (not computable from what's
    persisted today) and what payment_conversion_rate/cancellation_rate
    actually measure instead."""

    total_bookings: int
    bookings_by_status: dict[str, int]
    paid_bookings: int
    cancelled_bookings: int
    payment_conversion_rate: float
    cancellation_rate: float
    gross_revenue_by_currency: dict[str, Decimal]
    net_revenue_by_currency: dict[str, Decimal]
    revenue_by_day: list[DailyRevenuePointOut]
