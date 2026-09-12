"""
T-6 (docs/TASK_BOARD.md, Phase 9) dependency-free tests for
app/core/admin/analytics.py.

Runs the same way as tests/test_core_logic.py, tests/test_security_core.py,
tests/test_vapi_core.py, tests/test_payments_core.py, and
tests/test_notifications_core.py:

    python3 -m unittest tests.test_admin_core -v

No FastAPI/SQLAlchemy/Pydantic import anywhere in this file — that's the
point (confirmed by actually running this file with none of those
packages installed in this sandbox). app/services/{admin_service,
customer_service,call_service}.py (which DO need SQLAlchemy) and the new
HTTP routes (app/api/routes/{admin,customers,calls}.py) are NOT exercised
here — see docs/handoffs/2026-09-11-t6-admin-dashboard.md for the honest
accounting of what is and isn't actually executed this session. The
authorization logic these new routes depend on (authorize_staff_access)
is real, executed coverage too — see
tests/test_security_core.py::StaffAccessTests, not duplicated here.

Coverage focus: the arithmetic itself (rate calculations, multi-currency
grouping, net-vs-gross revenue, the zero-bookings edge case) — the part
of "admin analytics" where a real off-by-one or division-by-zero bug
would actually show up.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.core.admin.analytics import (
    AnalyticsSummary,
    BookingStatusSnapshot,
    DailyRevenuePoint,
    PaymentAmountSnapshot,
    build_analytics_summary,
    summarize_bookings,
    summarize_revenue,
)


def _dt(day: str) -> datetime:
    return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)


class SummarizeBookingsTests(unittest.TestCase):
    def test_empty_list_produces_zeros(self):
        total, counts, paid, cancelled = summarize_bookings([])
        self.assertEqual(total, 0)
        self.assertEqual(counts, {})
        self.assertEqual(paid, 0)
        self.assertEqual(cancelled, 0)

    def test_status_counts_and_totals(self):
        bookings = [
            BookingStatusSnapshot(status="CONFIRMED", payment_status="PAID", created_at=_dt("2026-09-01")),
            BookingStatusSnapshot(status="CONFIRMED", payment_status="UNPAID", created_at=_dt("2026-09-02")),
            BookingStatusSnapshot(status="CANCELLED", payment_status="REFUNDED", created_at=_dt("2026-09-03")),
            BookingStatusSnapshot(status="MODIFIED", payment_status="PAID", created_at=_dt("2026-09-04")),
        ]
        total, counts, paid, cancelled = summarize_bookings(bookings)
        self.assertEqual(total, 4)
        self.assertEqual(counts, {"CONFIRMED": 2, "CANCELLED": 1, "MODIFIED": 1})
        self.assertEqual(cancelled, 1)

    def test_refunded_counts_as_paid_for_conversion_purposes(self):
        # REFUNDED means money WAS collected at some point — see
        # analytics.py's module docstring for why this is deliberately
        # distinct from net revenue, which subtracts the refund back out.
        bookings = [BookingStatusSnapshot(status="CANCELLED", payment_status="REFUNDED", created_at=_dt("2026-09-01"))]
        _, _, paid, _ = summarize_bookings(bookings)
        self.assertEqual(paid, 1)

    def test_failed_and_unpaid_never_counted_as_paid(self):
        bookings = [
            BookingStatusSnapshot(status="FAILED", payment_status="UNPAID", created_at=_dt("2026-09-01")),
            BookingStatusSnapshot(status="CONFIRMED", payment_status="PENDING", created_at=_dt("2026-09-02")),
            BookingStatusSnapshot(status="CONFIRMED", payment_status="FAILED", created_at=_dt("2026-09-03")),
        ]
        _, _, paid, _ = summarize_bookings(bookings)
        self.assertEqual(paid, 0)


class SummarizeRevenueTests(unittest.TestCase):
    def test_empty_list_produces_empty_totals(self):
        gross, net, daily = summarize_revenue([])
        self.assertEqual(gross, {})
        self.assertEqual(net, {})
        self.assertEqual(daily, [])

    def test_gross_sums_per_currency_separately(self):
        payments = [
            PaymentAmountSnapshot(currency="EUR", amount=Decimal("100.00"), refunded_amount=None, created_at=_dt("2026-09-01")),
            PaymentAmountSnapshot(currency="EUR", amount=Decimal("50.00"), refunded_amount=None, created_at=_dt("2026-09-02")),
            PaymentAmountSnapshot(currency="USD", amount=Decimal("20.00"), refunded_amount=None, created_at=_dt("2026-09-01")),
        ]
        gross, _, _ = summarize_revenue(payments)
        # Different currencies are NEVER summed together — see module docstring.
        self.assertEqual(gross, {"EUR": Decimal("150.00"), "USD": Decimal("20.00")})

    def test_net_subtracts_refunded_amount(self):
        payments = [
            PaymentAmountSnapshot(currency="EUR", amount=Decimal("100.00"), refunded_amount=Decimal("30.00"), created_at=_dt("2026-09-01")),
        ]
        gross, net, _ = summarize_revenue(payments)
        self.assertEqual(gross["EUR"], Decimal("100.00"))
        self.assertEqual(net["EUR"], Decimal("70.00"))

    def test_none_refunded_amount_treated_as_zero(self):
        payments = [
            PaymentAmountSnapshot(currency="EUR", amount=Decimal("40.00"), refunded_amount=None, created_at=_dt("2026-09-01")),
        ]
        _, net, _ = summarize_revenue(payments)
        self.assertEqual(net["EUR"], Decimal("40.00"))

    def test_daily_points_grouped_by_day_and_currency_and_sorted(self):
        payments = [
            PaymentAmountSnapshot(currency="EUR", amount=Decimal("10.00"), refunded_amount=None, created_at=_dt("2026-09-02")),
            PaymentAmountSnapshot(currency="EUR", amount=Decimal("5.00"), refunded_amount=None, created_at=_dt("2026-09-01")),
            PaymentAmountSnapshot(currency="EUR", amount=Decimal("7.00"), refunded_amount=None, created_at=_dt("2026-09-01")),
            PaymentAmountSnapshot(currency="USD", amount=Decimal("3.00"), refunded_amount=None, created_at=_dt("2026-09-01")),
        ]
        _, _, daily = summarize_revenue(payments)
        self.assertEqual(
            daily,
            [
                DailyRevenuePoint(day="2026-09-01", currency="EUR", net_amount=Decimal("12.00")),
                DailyRevenuePoint(day="2026-09-01", currency="USD", net_amount=Decimal("3.00")),
                DailyRevenuePoint(day="2026-09-02", currency="EUR", net_amount=Decimal("10.00")),
            ],
        )


class BuildAnalyticsSummaryTests(unittest.TestCase):
    def test_zero_bookings_never_divides_by_zero(self):
        summary = build_analytics_summary([], [])
        self.assertIsInstance(summary, AnalyticsSummary)
        self.assertEqual(summary.total_bookings, 0)
        self.assertEqual(summary.payment_conversion_rate, 0.0)
        self.assertEqual(summary.cancellation_rate, 0.0)
        self.assertEqual(summary.gross_revenue_by_currency, {})

    def test_rates_computed_correctly(self):
        bookings = [
            BookingStatusSnapshot(status="CONFIRMED", payment_status="PAID", created_at=_dt("2026-09-01")),
            BookingStatusSnapshot(status="CONFIRMED", payment_status="UNPAID", created_at=_dt("2026-09-02")),
            BookingStatusSnapshot(status="CANCELLED", payment_status="REFUNDED", created_at=_dt("2026-09-03")),
            BookingStatusSnapshot(status="CANCELLED", payment_status="UNPAID", created_at=_dt("2026-09-04")),
        ]
        summary = build_analytics_summary(bookings, [])
        self.assertEqual(summary.total_bookings, 4)
        self.assertEqual(summary.paid_bookings, 2)  # PAID + REFUNDED
        self.assertEqual(summary.cancelled_bookings, 2)
        self.assertEqual(summary.payment_conversion_rate, 0.5)
        self.assertEqual(summary.cancellation_rate, 0.5)

    def test_revenue_flows_through_from_payments(self):
        bookings = [BookingStatusSnapshot(status="CONFIRMED", payment_status="PAID", created_at=_dt("2026-09-01"))]
        payments = [
            PaymentAmountSnapshot(currency="EUR", amount=Decimal("250.00"), refunded_amount=None, created_at=_dt("2026-09-01")),
        ]
        summary = build_analytics_summary(bookings, payments)
        self.assertEqual(summary.gross_revenue_by_currency["EUR"], Decimal("250.00"))
        self.assertEqual(summary.net_revenue_by_currency["EUR"], Decimal("250.00"))
        self.assertEqual(len(summary.revenue_by_day), 1)

    def test_bookings_by_status_reflects_only_statuses_actually_present(self):
        # Deliberately does NOT assert every value in
        # app.models.booking.BOOKING_STATUSES appears — most of those
        # (PENDING, TICKETED, CHECKED_IN, COMPLETED, CANCEL_REQUESTED,
        # MODIFICATION_PENDING, FAILED, EXPIRED) are reserved for future
        # workflows and are never actually written by any code path
        # today (confirmed by grep — see this module's docstring). A
        # dashboard reading this dict must not assume every key exists.
        bookings = [BookingStatusSnapshot(status="CONFIRMED", payment_status="PAID", created_at=_dt("2026-09-01"))]
        summary = build_analytics_summary(bookings, [])
        self.assertEqual(summary.bookings_by_status, {"CONFIRMED": 1})
        self.assertNotIn("PENDING", summary.bookings_by_status)


if __name__ == "__main__":
    unittest.main()
