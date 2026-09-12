"""
Admin dashboard — customers routes (Phase 9 — T-6, docs/TASK_BOARD.md).

GET /api/v1/customers is staff-only (see require_staff_permission's
docstring: CUSTOMERS_READ alone isn't enough there, because the bare
CUSTOMER role holds it too, for their own profile — see
app/core/security/ownership.py::authorize_staff_access). GET/PATCH
/{customer_id} reuse require_customer_profile_access exactly as Phase 4
built it — the boundary existed, unused, before this task; this is its
first caller.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps_auth import get_current_actor, require_customer_profile_access, require_staff_permission
from app.api.routes.admin import _admin_booking_out
from app.api.routes.bookings import _actor_label
from app.core.security.actor import CurrentActor
from app.core.security.rbac import Permission
from app.db.session import get_db
from app.models.customer import Customer
from app.schemas.common import make_page_meta, ok
from app.schemas.customer import CustomerDetailOut, CustomerListOut, CustomerOut, CustomerUpdateRequest
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


def _customer_out(c: Customer) -> CustomerOut:
    return CustomerOut(
        id=str(c.id), email=c.email, phone=c.phone, first_name=c.first_name, last_name=c.last_name,
        preferred_language=c.preferred_language, created_at=c.created_at,
    )


def _customer_detail_out(c: Customer) -> CustomerDetailOut:
    # Reuses _admin_booking_out from app/api/routes/admin.py, which
    # itself reuses _booking_out from app/api/routes/bookings.py — same
    # passport-masking discipline as the customer-facing booking detail
    # view, one code path, not a second implementation. See
    # AdminBookingOut's docstring (app/schemas/admin.py) for why this
    # needs the "admin" shape (booking id included) rather than plain
    # BookingOut here.
    return CustomerDetailOut(
        id=str(c.id), email=c.email, phone=c.phone, first_name=c.first_name, last_name=c.last_name,
        preferred_language=c.preferred_language, created_at=c.created_at,
        bookings=[_admin_booking_out(b) for b in c.bookings],
    )


@router.get("")
def list_customers(
    request: Request,
    search: Optional[str] = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(require_staff_permission(Permission.CUSTOMERS_READ.value)),
):
    items, total = CustomerService(db).list_customers(search=search, limit=limit, offset=offset)
    body = CustomerListOut(
        items=[_customer_out(c) for c in items],
        page=make_page_meta(limit=limit, offset=offset, total=total),
    )
    return ok(body, request.state.request_id)


@router.get("/{customer_id}")
def get_customer(
    customer_id: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    service = CustomerService(db)
    customer = service.get_customer(customer_id)
    actor = require_customer_profile_access(
        actor, target_customer_id=str(customer.id), permission=Permission.CUSTOMERS_READ.value
    )
    return ok(_customer_detail_out(customer), request.state.request_id)


@router.patch("/{customer_id}")
def update_customer(
    customer_id: str,
    update: CustomerUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    """The one write T-6 adds (see CustomerUpdateRequest's docstring on
    why it's deliberately narrow). Reachable by the owning customer
    (CUSTOMERS_MANAGE, which Role.CUSTOMER also holds — see rbac.py) OR
    by staff — require_customer_profile_access already distinguishes the
    two the same way it does for CUSTOMERS_READ above."""
    service = CustomerService(db)
    customer = service.get_customer(customer_id)
    actor = require_customer_profile_access(
        actor, target_customer_id=str(customer.id), permission=Permission.CUSTOMERS_MANAGE.value
    )
    actor_type = "customer" if actor.customer_id == str(customer.id) else "admin"
    updated = service.update_customer(
        customer_id, update, actor=_actor_label(actor, None), actor_type=actor_type,
        request_id=request.state.request_id,
    )
    return ok(_customer_detail_out(updated), request.state.request_id)
