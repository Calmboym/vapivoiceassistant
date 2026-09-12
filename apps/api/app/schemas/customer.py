from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.admin import AdminBookingOut
from app.schemas.common import PageMeta


class CustomerOut(BaseModel):
    id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    preferred_language: str
    created_at: datetime


class CustomerDetailOut(CustomerOut):
    """Adds this customer's own bookings, as AdminBookingOut (adds the
    booking id needed to link to a detail page — see
    app/schemas/admin.py::AdminBookingOut's own docstring) built through
    the same passport-masking discipline as the customer-facing booking
    detail view (app/api/routes/bookings.py's _masked_passport, which
    app/api/routes/admin.py and app/api/routes/customers.py both call
    through to — not a second implementation)."""

    bookings: list[AdminBookingOut] = Field(default_factory=list)


class CustomerListOut(BaseModel):
    items: list[CustomerOut]
    page: PageMeta


class CustomerUpdateRequest(BaseModel):
    """Partial update (PATCH semantics) — every field optional, only
    the ones supplied are changed. Contact-info correction only (§ T-6
    scope: 'read-heavy... manage surface on top of what exists' — this
    is the one write this task adds, deliberately narrow). Does NOT
    accept preferred_language (no UI need identified for T-6) or an
    email/phone pair that collides with another existing customer row
    (enforced by the DB's existing unique constraint on Customer.email,
    surfaced as a normal 409 by the service layer, not duplicated here)."""

    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=6, max_length=32)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
