from __future__ import annotations

import uuid

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Aircraft(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "aircraft"

    registration: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    aircraft_type: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # commercial | charter
    seat_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    range_km: Mapped[int] = mapped_column(Integer, nullable=False)
    baggage_capacity_kg: Mapped[int] = mapped_column(Integer, nullable=False)
    cabin_configuration: Mapped[str] = mapped_column(String(100), nullable=False)
    amenities: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="available", nullable=False)
    current_location: Mapped[str] = mapped_column(String(3), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Aircraft {self.registration} {self.model}>"
