from __future__ import annotations

from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.customer import Customer


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_email_or_phone(self, email: Optional[str], phone: Optional[str]) -> Optional[Customer]:
        if not email and not phone:
            return None
        conditions = []
        if email:
            conditions.append(Customer.email == email)
        if phone:
            conditions.append(Customer.phone == phone)
        return self.db.scalar(select(Customer).where(or_(*conditions)))

    def get_or_create(self, email: Optional[str], phone: Optional[str]) -> Customer:
        existing = self.find_by_email_or_phone(email, phone)
        if existing:
            return existing
        customer = Customer(email=email, phone=phone)
        self.db.add(customer)
        self.db.flush()
        return customer

    # --- Phase 9 (T-6) admin dashboard additions below ---

    def get_by_id(self, customer_id: str) -> Optional[Customer]:
        return self.db.get(Customer, customer_id)

    def list_admin(self, *, search: Optional[str] = None, limit: int = 20, offset: int = 0) -> list[Customer]:
        """Staff-facing list — see app/services/customer_service.py and
        app/api/routes/customers.py for the require_staff_permission()
        gate that must sit in front of this (this method itself has no
        access-control awareness, same as every other repository in this
        codebase — see MASTER_RULES.md §2: authorization decisions never
        live in the data-access layer)."""
        stmt = select(Customer).order_by(Customer.created_at.desc())
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Customer.email.ilike(like),
                    Customer.phone.ilike(like),
                    Customer.first_name.ilike(like),
                    Customer.last_name.ilike(like),
                )
            )
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def count_admin(self, *, search: Optional[str] = None) -> int:
        stmt = select(func.count()).select_from(Customer)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Customer.email.ilike(like),
                    Customer.phone.ilike(like),
                    Customer.first_name.ilike(like),
                    Customer.last_name.ilike(like),
                )
            )
        return self.db.scalar(stmt) or 0
