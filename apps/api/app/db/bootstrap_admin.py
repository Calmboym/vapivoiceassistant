"""
One-time admin bootstrap (§16).

Run with:  python -m app.db.bootstrap_admin
(from apps/api/, after `alembic upgrade head` and `python -m app.db.seed`)

Does NOTHING unless BOOTSTRAP_ADMIN_ENABLED=true, BOOTSTRAP_ADMIN_EMAIL,
and BOOTSTRAP_ADMIN_PASSWORD are all set in the environment — there is no
hard-coded admin/admin fallback, and `Settings.validate_for_production()`
(app/core/config.py) additionally refuses to even START the app in
production if BOOTSTRAP_ADMIN_ENABLED is left on, so this can't
accidentally ship live.

Idempotent: re-running against an email that already exists updates that
user's role to SUPER_ADMIN (useful for promoting an existing account)
rather than erroring or creating a duplicate.
"""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security.password_policy import validate_password_strength
from app.core.security.passwords import default_password_hasher
from app.core.security.rbac import Role
from app.db.session import session_scope
from app.models.user import User
from app.repositories.rbac_repository import RbacRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import record_audit_event

logger = get_logger(__name__)


def run() -> int:
    settings = get_settings()

    if not settings.bootstrap_admin_enabled:
        print("BOOTSTRAP_ADMIN_ENABLED is not true — refusing to run. Nothing done.")
        return 1

    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        print("BOOTSTRAP_ADMIN_ENABLED=true but BOOTSTRAP_ADMIN_EMAIL/BOOTSTRAP_ADMIN_PASSWORD are not both set.")
        return 1

    email = settings.bootstrap_admin_email.strip().lower()
    policy = validate_password_strength(settings.bootstrap_admin_password, email=email)
    if not policy.valid:
        print("BOOTSTRAP_ADMIN_PASSWORD does not meet the password policy:")
        for problem in policy.problems:
            print(f"  - {problem}")
        return 1

    with session_scope() as db:
        users = UserRepository(db)
        rbac = RbacRepository(db)
        user = users.get_by_email(email)
        if user is None:
            user = User(
                email=email,
                password_hash=default_password_hasher.hash(settings.bootstrap_admin_password),
                status="ACTIVE",
                email_verified=True,
            )
            users.add(user)
            action = "bootstrap.admin_created"
        else:
            action = "bootstrap.admin_promoted"

        rbac.assign_role(user.id, Role.SUPER_ADMIN)
        record_audit_event(
            db, actor="system:bootstrap", actor_type="system", action=action,
            resource="user", resource_id=str(user.id), metadata={"email": email},
        )

    print(f"OK: {email} now has the SUPER_ADMIN role.")
    print("Remember to unset BOOTSTRAP_ADMIN_ENABLED/BOOTSTRAP_ADMIN_PASSWORD when you're done.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
