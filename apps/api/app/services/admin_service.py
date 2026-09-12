"""
Staff-facing admin dashboard service (Phase 9 — T-6, docs/TASK_BOARD.md):
cross-customer bookings list/detail (with full audit trail), and
revenue/booking analytics. Read-only — see
app/services/call_service.py's and customer_service.py's module
docstrings for the same "T-6 does not change booking/payment/Vapi
business logic" boundary; this file is no different.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.admin.analytics import (
    AnalyticsSummary,
    BookingStatusSnapshot,
    PaymentAmountSnapshot,
    build_analytics_summary,
)
from app.core.exceptions import NotFoundError
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.models.payment import Payment
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.booking_repository import BookingRepository
from app.repositories.payment_repository import PaymentRepository


class AdminService:
    def __init__(self, db: Session):
        self.db = db
        self.bookings = BookingRepository(db)
        self.payments = PaymentRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def get_booking(self, booking_id: str) -> Booking:
        booking = self.bookings.get_by_id(booking_id)
        if booking is None:
            raise NotFoundError("BOOKING_NOT_FOUND", "No booking found with that id.")
        return booking

    def list_bookings(
        self,
        *,
        status: Optional[str] = None,
        customer_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> "tuple[list[Booking], int]":
        items = self.bookings.list_admin(status=status, customer_id=customer_id, limit=limit, offset=offset)
        total = self.bookings.count_admin(status=status, customer_id=customer_id)
        return items, total

    def get_booking_detail(self, booking_id: str) -> "tuple[Booking, list[Payment], list[AuditLog]]":
        """Returns (booking, payments, audit_trail) — see
        app/schemas/admin.py::AdminBookingDetailOut, which
        app/api/routes/admin.py assembles this tuple into. Every payment
        attempt against the booking is included, not just the latest
        (see PaymentRepository.list_for_booking's own docstring on why a
        FAILED attempt followed by a later SUCCEEDED one are both kept).

        The audit-trail lookup queries AuditLog.resource_id by BOTH
        booking.pnr AND str(booking.id) and merges the results
        (de-duplicated by AuditLog.id, sorted chronologically) — even
        though, confirmed by grep across every current
        resource="booking" record_audit_event() call site
        (booking_service.py, cancellation_service.py,
        passenger_service.py — all of them, no exceptions), every single
        one passes resource_id=pnr, never resource_id=str(booking.id).
        So today, the str(booking.id) query always returns zero rows —
        it is NOT covering split pre-existing data, there isn't any. It
        is purely defensive: AuditLog.resource_id is an unconstrained
        String column with no format enforced at write time, and this
        endpoint's whole purpose (WBS-5's exit criterion: "see a
        booking's full audit trail") breaks silently, with no error, the
        day a future call site inconsistently writes resource_id=str(
        booking.id) instead of pnr — a bug that would be invisible
        without this merge already in place. Normalizing every existing
        writer onto one shape (a data migration) would be a real fix but
        is a schema/data change outside T-6's authorized scope — see
        docs/handoffs/2026-09-11-t6-admin-dashboard.md, 'Pre-existing
        issues discovered but NOT fixed.'"""
        booking = self.get_booking(booking_id)
        payments = self.payments.list_for_booking(booking.id)

        by_id = self.audit_logs.list_for_resource("booking", str(booking.id))
        by_pnr = self.audit_logs.list_for_resource("booking", booking.pnr)
        seen_ids = {entry.id for entry in by_id}
        merged = by_id + [entry for entry in by_pnr if entry.id not in seen_ids]
        audit_trail = sorted(merged, key=lambda entry: entry.created_at)

        return booking, payments, audit_trail

    def get_analytics_summary(self, *, since: Optional[datetime] = None) -> AnalyticsSummary:
        """Fetches raw rows (needs a real DB — written, not executed in
        this sandbox) and converts them into the plain, dependency-free
        snapshot dataclasses that app.core.admin.analytics actually does
        the arithmetic on (that module IS executed and tested here — see
        tests/test_admin_core.py). This conversion step is the entire
        reason analytics.py exists as a separate module rather than
        computing rates inline here: the arithmetic gets real, executed
        test coverage this way even though the query surrounding it
        can't run in this sandbox."""
        bookings = [
            BookingStatusSnapshot(status=b.status, payment_status=b.payment_status, created_at=b.created_at)
            for b in self.bookings.list_for_analytics(since=since)
        ]
        payments = [
            PaymentAmountSnapshot(
                currency=p.currency, amount=p.amount, refunded_amount=p.refunded_amount, created_at=p.created_at,
            )
            for p in self.payments.list_succeeded_since(since=since)
        ]
        return build_analytics_summary(bookings, payments)
