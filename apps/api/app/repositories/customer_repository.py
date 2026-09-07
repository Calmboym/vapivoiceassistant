from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select
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
