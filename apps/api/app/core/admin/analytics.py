"""
Pure, dependency-free analytics calculations for the admin dashboard
(Phase 9 — T-6, docs/TASK_BOARD.md).

Mirrors app/core/notifications/content.py's discipline exactly: stdlib
only (dataclasses, datetime, decimal, collections, typing) so the
arithmetic that actually matters here gets real, executed test coverage
in this sandbox — the same reasoning that applied to booking-confirmation
email content in T-5 and refund math in T-3. Callers
(app/services/admin_service.py) convert SQLAlchemy Booking/Payment ORM
rows into the plain snapshot dataclasses below BEFORE calling into this
module; this module never imports app.models.* or SQLAlchemy, on
purpose, so it stays testable here without a database.

Honesty note (MASTER_RULES.md §1 — "never invent... if the backend
doesn't have it, say so honestly"): the Master Build Prompt's original
idea of a "quote conversion rate" (what fraction of fare QUOTES become
real bookings) is NOT something this schema can compute today. A fare
quote a caller never acts on is never persisted as a Booking row at all
— confirmed by reading app/services/booking_service.py: create_booking()
writes status="CONFIRMED" directly, and "QUOTE" (present in
app.models.booking.BOOKING_STATUSES) is never actually assigned to a
stored Booking.status by any code path in this codebase today. An
abandoned quote simply expires in FlightService's in-memory cache and
leaves no row behind to count. Tracking real quote-to-booking conversion
would need a new persisted "quote attempt" record — a schema change,
which is explicitly out of T-6's scope (see docs/TASK_BOARD.md's T-6
entry: "NOT in scope: any change to booking/payment/Vapi business
logic"). Rather than fabricate a conversion number from data that
doesn't exist, this module reports what IS honestly computable from what
Booking/Payment already persist: a booking-status breakdown, a PAYMENT
conversion rate (created bookings that ever reached a paid state), a
cancellation rate, and revenue computed from actually-SUCCEEDED Payment
rows (never from Booking.total_price, which is a quoted/snapshotted
price, not proof money was actually collected).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

# A booking counts as "paid" for the conversion-rate calculation using
# Booking.payment_status in this set. REFUNDED is included deliberately:
# money WAS collected at some point for that booking, it was just later
# returned — that's a different question from net revenue (below), which
# subtracts refunds back out. See app/models/booking.py's PAYMENT_STATUSES.
_PAID_PAYMENT_STATUSES = frozenset({"PAID", "REFUNDED"})


@dataclass(frozen=True)
class BookingStatusSnapshot:
    """One Booking row's analytics-relevant fields only — deliberately
    narrow, same "don't hand a pure function more than it needs"
    discipline as app.core.notifications.content.PassengerSummary."""

    status: str
    payment_status: str
    created_at: datetime


@dataclass(frozen=True)
class PaymentAmountSnapshot:
    """One SUCCEEDED Payment row's amount fields. The caller
    (AdminService) is responsible for only ever constructing this from a
    Payment whose status == "SUCCEEDED" — this module does no status
    filtering itself, since Payment.status isn't part of the snapshot at
    all (a snapshot without it can't accidentally include a PENDING/
    FAILED payment in a revenue total by forgetting a filter here)."""

    currency: str
    amount: Decimal
    refunded_amount: Optional[Decimal]
    created_at: datetime


@dataclass(frozen=True)
class DailyRevenuePoint:
    day: str  # "YYYY-MM-DD", UTC
    currency: str
    net_amount: Decimal


@dataclass(frozen=True)
class AnalyticsSummary:
    total_bookings: int
    bookings_by_status: dict[str, int]
    paid_bookings: int
    cancelled_bookings: int
    payment_conversion_rate: float  # paid_bookings / total_bookings; 0.0 if no bookings exist yet
    cancellation_rate: float  # cancelled_bookings / total_bookings; 0.0 if no bookings exist yet
    gross_revenue_by_currency: dict[str, Decimal]  # sum of SUCCEEDED Payment.amount
    net_revenue_by_currency: dict[str, Decimal]  # gross minus refunded_amount
    revenue_by_day: list[DailyRevenuePoint]


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def summarize_bookings(
    bookings: "list[BookingStatusSnapshot]",
) -> "tuple[int, dict[str, int], int, int]":
    """Returns (total, status_counts, paid_count, cancelled_count). Pure
    counting only — rate math (division, zero-booking edge case) lives
    in build_analytics_summary below, not here, so this stays trivially
    correct and separately testable."""
    total = len(bookings)
    status_counts: dict[str, int] = dict(Counter(b.status for b in bookings))
    paid_count = sum(1 for b in bookings if b.payment_status in _PAID_PAYMENT_STATUSES)
    cancelled_count = status_counts.get("CANCELLED", 0)
    return total, status_counts, paid_count, cancelled_count


def summarize_revenue(
    payments: "list[PaymentAmountSnapshot]",
) -> "tuple[dict[str, Decimal], dict[str, Decimal], list[DailyRevenuePoint]]":
    """Returns (gross_by_currency, net_by_currency, daily_points), each
    keyed/grouped by currency — amounts in different currencies are
    never summed together (a EUR total and a USD total staying separate
    is the only honest way to report "total revenue" for a
    multi-currency booking set; see app/models/booking.py's per-booking
    `currency` field)."""
    gross: dict[str, Decimal] = {}
    net: dict[str, Decimal] = {}
    daily: dict[tuple[str, str], Decimal] = {}

    for p in payments:
        gross[p.currency] = gross.get(p.currency, Decimal("0")) + p.amount
        net_amount = p.amount - (p.refunded_amount or Decimal("0"))
        net[p.currency] = net.get(p.currency, Decimal("0")) + net_amount

        day_key = p.created_at.strftime("%Y-%m-%d")
        daily_key = (day_key, p.currency)
        daily[daily_key] = daily.get(daily_key, Decimal("0")) + net_amount

    daily_points = [
        DailyRevenuePoint(day=day, currency=currency, net_amount=amount)
        for (day, currency), amount in sorted(daily.items())
    ]
    return gross, net, daily_points


def build_analytics_summary(
    bookings: "list[BookingStatusSnapshot]",
    payments: "list[PaymentAmountSnapshot]",
) -> AnalyticsSummary:
    total, status_counts, paid_count, cancelled_count = summarize_bookings(bookings)
    gross, net, daily_points = summarize_revenue(payments)
    return AnalyticsSummary(
        total_bookings=total,
        bookings_by_status=status_counts,
        paid_bookings=paid_count,
        cancelled_bookings=cancelled_count,
        payment_conversion_rate=_safe_rate(paid_count, total),
        cancellation_rate=_safe_rate(cancelled_count, total),
        gross_revenue_by_currency=gross,
        net_revenue_by_currency=net,
        revenue_by_day=daily_points,
    )
