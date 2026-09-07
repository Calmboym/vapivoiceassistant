from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Phase 4 spec §7.
USER_STATUSES = ("ACTIVE", "SUSPENDED", "DISABLED", "PENDING_VERIFICATION")


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A login-capable identity (§3). Deliberately separate from
    `Customer` (app.models.customer): a Customer is a booking *contact
    record*, created ad-hoc and with no password the moment someone
    books a flight (see CustomerRepository.get_or_create, used by
    BookingService with no auth at all) — that stays true post-Phase-4,
    since a caller can still book without ever creating an account, per
    docs/BOOKING_FLOW.md. A User is what *authenticates*: it optionally
    links to one Customer via `customer_id` once that person registers
    an account (see AuthService.register), and staff/admin Users simply
    never get a customer_id at all.

    `password_hash` is never serialized into any Pydantic response model
    (see app/schemas/auth.py — UserOut deliberately has no such field)
    and is never logged (see app.core.security.redaction, which matches
    on the literal substring "password").
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="PENDING_VERIFICATION", nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("customers.id"), nullable=True, index=True
    )
    customer: Mapped[Optional["Customer"]] = relationship()

    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    role_assignments: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.id} {self.email}>"
