from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking


class BookingRepository:
    def __init__(self, db: Session):
        self.db = db

    def pnr_exists(self, pnr: str) -> bool:
        return self.db.scalar(select(Booking.id).where(Booking.pnr == pnr)) is not None

    def get_by_pnr(self, pnr: str) -> Optional[Booking]:
        return self.db.scalar(select(Booking).where(Booking.pnr == pnr))

    def add(self, booking: Booking) -> Booking:
        self.db.add(booking)
        self.db.flush()  # assigns the PK without committing the outer transaction
        return booking

    def list_for_customer(self, customer_id) -> list[Booking]:
        return list(self.db.scalars(select(Booking).where(Booking.customer_id == customer_id)))
