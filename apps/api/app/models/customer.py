from __future__ import annotations

from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customers"

    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="customer")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Customer {self.id} {self.email or self.phone}>"
