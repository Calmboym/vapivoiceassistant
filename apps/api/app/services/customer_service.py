"""
Admin-facing customer read/update service (Phase 9 — T-6,
docs/TASK_BOARD.md). Permission-agnostic on purpose, same discipline as
every other service in this codebase (RBACService, PassengerService,
...) — see MASTER_RULES.md §2: authorization decisions belong in
app/core/security/*.py and get enforced by a FastAPI dependency BEFORE a
route handler ever calls into this service, never re-checked here.
app/api/routes/customers.py is the only caller.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.customer import Customer
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import CustomerUpdateRequest
from app.services.audit_service import record_audit_event


class CustomerService:
    def __init__(self, db: Session):
        self.db = db
        self.customers = CustomerRepository(db)

    def get_customer(self, customer_id: str) -> Customer:
        customer = self.customers.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("CUSTOMER_NOT_FOUND", "No customer found with that id.")
        return customer

    def list_customers(
        self, *, search: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> "tuple[list[Customer], int]":
        items = self.customers.list_admin(search=search, limit=limit, offset=offset)
        total = self.customers.count_admin(search=search)
        return items, total

    def update_customer(
        self,
        customer_id: str,
        update: CustomerUpdateRequest,
        *,
        actor: str,
        actor_type: str = "admin",
        request_id: Optional[str] = None,
    ) -> Customer:
        """Applies only the fields the caller actually supplied (PATCH
        semantics — see CustomerUpdateRequest's docstring). `actor_type`
        defaults to "admin" (the staff path) but accepts an override so
        the SAME method also serves a customer editing their OWN profile
        via require_customer_profile_access (app/api/deps_auth.py) —
        see app/api/routes/customers.py, which passes actor_type=
        "customer" for that case. Either way the resulting AuditLog row
        honestly reflects who actually made the change."""
        customer = self.get_customer(customer_id)
        changed_fields: dict = {}

        if update.email is not None and update.email != customer.email:
            collision = self.customers.find_by_email_or_phone(update.email, None)
            if collision is not None and str(collision.id) != str(customer.id):
                raise ConflictError("CUSTOMER_EMAIL_ALREADY_EXISTS", "Another customer already uses that email.")
            customer.email = update.email
            changed_fields["email"] = update.email
        if update.phone is not None and update.phone != customer.phone:
            customer.phone = update.phone
            changed_fields["phone"] = update.phone
        if update.first_name is not None and update.first_name != customer.first_name:
            customer.first_name = update.first_name
            changed_fields["first_name"] = update.first_name
        if update.last_name is not None and update.last_name != customer.last_name:
            customer.last_name = update.last_name
            changed_fields["last_name"] = update.last_name

        if changed_fields:
            # Field NAMES only in the audit trail, never old/new values —
            # same discipline as every other record_audit_event call in
            # this codebase (e.g. passenger.passport_updated never logs
            # the passport number itself). A staff member correcting a
            # customer's email/phone is exactly the kind of action that
            # belongs in the trail; the actual new value is already
            # visible on the customer's own record for anyone with
            # customers.read.
            record_audit_event(
                self.db, actor=actor, actor_type=actor_type, action="customer.updated",
                resource="customer", resource_id=str(customer.id), request_id=request_id,
                metadata={"fields_changed": sorted(changed_fields.keys())},
            )
            self.db.commit()
        return customer
