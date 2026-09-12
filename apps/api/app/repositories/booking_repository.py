from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
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

    # --- Phase 9 (T-6) admin dashboard additions below ---

    def get_by_id(self, booking_id) -> Optional[Booking]:
        """Internal UUID primary key — the admin bookings list links to
        a detail view by this id, not by PNR (a customer-facing PNR
        lookup goes through get_by_pnr above and is a DIFFERENT,
        ownership-gated code path — see app/api/routes/bookings.py)."""
        return self.db.get(Booking, booking_id)

    def list_admin(
        self,
        *,
        status: Optional[str] = None,
        customer_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Booking]:
        stmt = select(Booking).order_by(Booking.created_at.desc())
        if status:
            stmt = stmt.where(Booking.status == status)
        if customer_id:
            stmt = stmt.where(Booking.customer_id == customer_id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def count_admin(self, *, status: Optional[str] = None, customer_id: Optional[str] = None) -> int:
        stmt = select(func.count()).select_from(Booking)
        if status:
            stmt = stmt.where(Booking.status == status)
        if customer_id:
            stmt = stmt.where(Booking.customer_id == customer_id)
        return self.db.scalar(stmt) or 0

    def list_for_analytics(self, *, since: Optional[datetime] = None) -> list[Booking]:
        """Unpaginated, full-row fetch feeding
        app/services/admin_service.py's AnalyticsSummary. Deliberately
        separate from list_admin above (which is paginated for the
        bookings-list PAGE, a different use) — an analytics summary
        needs every row in range to count correctly, not one page of
        them. Fine at this project's current scale; would need a
        SQL-side aggregate query instead of Python-side counting if the
        bookings table ever grows large enough for that to matter (not
        the case here — see docs/handoffs/2026-09-11-t6-admin-dashboard.md,
        Known limitations)."""
        stmt = select(Booking)
        if since is not None:
            stmt = stmt.where(Booking.created_at >= since)
        return list(self.db.scalars(stmt))
