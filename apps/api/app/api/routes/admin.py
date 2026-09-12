"""
Admin dashboard — bookings/audit-trail/analytics routes (Phase 9 — T-6,
docs/TASK_BOARD.md). All three endpoints below are gated on
Permission.ADMIN_READ alone (no require_staff_permission() needed — only
Role.ADMIN/SUPER_ADMIN ever hold admin.read; see rbac.py's
ROLE_PERMISSIONS and
tests/test_security_core.py::RbacTests::test_customer_role_never_holds_admin_or_calls_permissions).

docs/TASK_BOARD.md's T-6 entry names this namespace's permissions as
"admin.*" specifically (not bookings.read/payments.read) — so a FINANCE
or SUPPORT_AGENT role, despite holding BOOKINGS_READ/PAYMENTS_READ, does
NOT get this view by that route alone. Whether FINANCE should reach
these bookings/analytics views is a product decision outside what T-6's
task-board scope actually authorizes; see this task's handoff, "Deferred
items," rather than this file quietly deciding it.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps_auth import require_permission
from app.api.routes.bookings import _booking_out
from app.core.security.actor import CurrentActor
from app.core.security.rbac import Permission
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.payment import Payment
from app.schemas.admin import (
    AdminBookingDetailOut,
    AdminBookingListOut,
    AdminBookingOut,
    AnalyticsSummaryOut,
    AuditLogEntryOut,
    DailyRevenuePointOut,
    PaymentSummaryOut,
)
from app.schemas.common import make_page_meta, ok
from app.services.admin_service import AdminService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _admin_booking_out(b) -> AdminBookingOut:
    """_booking_out(b) (app/api/routes/bookings.py) plus the id/customer_id
    a staff list/detail view needs — see AdminBookingOut's own docstring
    for why this is layered on top rather than changing BookingOut
    itself. `b.customer` is the existing back_populates relationship
    (app/models/customer.py) — already loaded by BookingRepository's
    admin queries in the same session, no extra query here."""
    return AdminBookingOut(
        **_booking_out(b).model_dump(),
        id=str(b.id), customer_id=str(b.customer_id),
        customer_email=(b.customer.email if b.customer else None),
    )


def _payment_summary_out(p: Payment) -> PaymentSummaryOut:
    return PaymentSummaryOut(
        id=str(p.id), status=p.status, amount=p.amount, currency=p.currency, provider_name=p.provider_name,
        provider_payment_intent_id=p.provider_payment_intent_id, refunded_amount=p.refunded_amount,
        refund_status=p.refund_status, refund_reason=p.refund_reason, failure_code=p.failure_code,
        failure_message=p.failure_message, created_at=p.created_at, completed_at=p.completed_at,
    )


def _audit_entry_out(a: AuditLog) -> AuditLogEntryOut:
    return AuditLogEntryOut(
        id=str(a.id), actor=a.actor, actor_type=a.actor_type, action=a.action, resource=a.resource,
        resource_id=a.resource_id, call_id=a.call_id, event_metadata=a.event_metadata, created_at=a.created_at,
    )


@router.get("/bookings")
def list_bookings(
    request: Request,
    status: Optional[str] = Query(default=None, max_length=30),
    customer_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(require_permission(Permission.ADMIN_READ.value)),
):
    items, total = AdminService(db).list_bookings(status=status, customer_id=customer_id, limit=limit, offset=offset)
    body = AdminBookingListOut(
        items=[_admin_booking_out(b) for b in items],
        page=make_page_meta(limit=limit, offset=offset, total=total),
    )
    return ok(body, request.state.request_id)


@router.get("/bookings/{booking_id}")
def get_booking_detail(
    booking_id: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(require_permission(Permission.ADMIN_READ.value)),
):
    """WBS-5's exit criterion: "see a booking's full audit trail." See
    AdminService.get_booking_detail's docstring for why the audit-trail
    lookup merges two queries (booking.id AND booking.pnr) rather than
    one."""
    booking, payments, audit_trail = AdminService(db).get_booking_detail(booking_id)
    body = AdminBookingDetailOut(
        booking=_admin_booking_out(booking),
        payments=[_payment_summary_out(p) for p in payments],
        audit_trail=[_audit_entry_out(a) for a in audit_trail],
    )
    return ok(body, request.state.request_id)


@router.get("/analytics")
def get_analytics(
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(require_permission(Permission.ADMIN_READ.value)),
):
    """See app/core/admin/analytics.py's module docstring for exactly
    what this does and does NOT measure (notably: no "quote conversion
    rate" — not computable from what's persisted today)."""
    summary = AdminService(db).get_analytics_summary()
    body = AnalyticsSummaryOut(
        total_bookings=summary.total_bookings,
        bookings_by_status=summary.bookings_by_status,
        paid_bookings=summary.paid_bookings,
        cancelled_bookings=summary.cancelled_bookings,
        payment_conversion_rate=summary.payment_conversion_rate,
        cancellation_rate=summary.cancellation_rate,
        gross_revenue_by_currency=summary.gross_revenue_by_currency,
        net_revenue_by_currency=summary.net_revenue_by_currency,
        revenue_by_day=[
            DailyRevenuePointOut(day=p.day, currency=p.currency, net_amount=p.net_amount)
            for p in summary.revenue_by_day
        ],
    )
    return ok(body, request.state.request_id)
