"""
Roles, permissions, and the role -> permission matrix (Phase 4 spec §7, §8).

Deliberately dependency-free (stdlib only) so the whole authorization
matrix is unit-testable without a database — see
tests/test_security_core.py::RbacTests. The DB-backed layer
(app/models/rbac.py, app/services/rbac_service.py) exists so an admin can
override a user's *effective* permissions per-deployment, but the matrix
below is the sane, secure-by-default starting point and is what
`app/db/seed.py`-equivalent bootstrap logic loads into the `roles` /
`permissions` / `role_permissions` tables.

Design note (§8: "Do not use role names as the only authorization
mechanism. Use explicit permissions."): every authorization check in this
codebase (see ownership.py, api/deps.py) checks a *permission string*
(e.g. "bookings.cancel"), never a role name directly. Roles are only a
convenient way to assign a bundle of permissions to a user.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    CUSTOMER = "CUSTOMER"
    SUPPORT_AGENT = "SUPPORT_AGENT"
    BOOKING_AGENT = "BOOKING_AGENT"
    FINANCE = "FINANCE"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"
    READ_ONLY = "READ_ONLY"


class Permission(str, Enum):
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    CUSTOMERS_READ = "customers.read"
    CUSTOMERS_MANAGE = "customers.manage"
    PASSENGERS_READ = "passengers.read"
    PASSENGERS_MANAGE = "passengers.manage"
    FLIGHTS_READ = "flights.read"
    FLIGHTS_MANAGE = "flights.manage"
    BOOKINGS_READ = "bookings.read"
    BOOKINGS_CREATE = "bookings.create"
    BOOKINGS_MODIFY = "bookings.modify"
    BOOKINGS_CANCEL = "bookings.cancel"
    PAYMENTS_READ = "payments.read"
    PAYMENTS_CREATE = "payments.create"
    PAYMENTS_REFUND = "payments.refund"
    CALLS_READ = "calls.read"
    CALLS_MANAGE = "calls.manage"
    SUPPORT_READ = "support.read"
    SUPPORT_MANAGE = "support.manage"
    VAPI_EXECUTE = "vapi.execute"
    VAPI_CONFIGURE = "vapi.configure"
    ADMIN_READ = "admin.read"
    ADMIN_MANAGE = "admin.manage"
    SYSTEM_MANAGE = "system.manage"
    AUDIT_READ = "audit.read"
    AUDIT_EXPORT = "audit.export"


ALL_PERMISSIONS: frozenset[str] = frozenset(p.value for p in Permission)

_P = Permission  # local alias to keep the table below readable

# The default role -> permission bundle. A customer's *ownership* scope
# (their own bookings only) is enforced separately, in ownership.py — a
# permission here means "can perform this kind of action at all", not
# "can perform it on anything". See §10/§11.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.CUSTOMER: frozenset({
        _P.CUSTOMERS_READ, _P.CUSTOMERS_MANAGE,
        _P.BOOKINGS_READ, _P.BOOKINGS_CREATE, _P.BOOKINGS_MODIFY, _P.BOOKINGS_CANCEL,
        _P.PASSENGERS_READ, _P.PASSENGERS_MANAGE,
        _P.PAYMENTS_READ, _P.PAYMENTS_CREATE,
        _P.FLIGHTS_READ,
    }),
    Role.READ_ONLY: frozenset({
        _P.USERS_READ, _P.CUSTOMERS_READ, _P.PASSENGERS_READ, _P.FLIGHTS_READ,
        _P.BOOKINGS_READ, _P.PAYMENTS_READ, _P.CALLS_READ, _P.SUPPORT_READ, _P.AUDIT_READ,
    }),
    Role.SUPPORT_AGENT: frozenset({
        _P.CUSTOMERS_READ, _P.PASSENGERS_READ, _P.FLIGHTS_READ,
        _P.BOOKINGS_READ, _P.BOOKINGS_MODIFY, _P.BOOKINGS_CANCEL,
        _P.CALLS_READ, _P.CALLS_MANAGE, _P.SUPPORT_READ, _P.SUPPORT_MANAGE,
    }),
    Role.BOOKING_AGENT: frozenset({
        _P.CUSTOMERS_READ, _P.PASSENGERS_READ, _P.PASSENGERS_MANAGE, _P.FLIGHTS_READ,
        _P.BOOKINGS_READ, _P.BOOKINGS_CREATE, _P.BOOKINGS_MODIFY, _P.BOOKINGS_CANCEL,
    }),
    Role.FINANCE: frozenset({
        _P.BOOKINGS_READ, _P.PAYMENTS_READ, _P.PAYMENTS_CREATE, _P.PAYMENTS_REFUND, _P.AUDIT_READ,
    }),
    Role.ADMIN: frozenset({
        _P.USERS_READ, _P.USERS_MANAGE, _P.CUSTOMERS_READ, _P.CUSTOMERS_MANAGE,
        _P.PASSENGERS_READ, _P.PASSENGERS_MANAGE, _P.FLIGHTS_READ, _P.FLIGHTS_MANAGE,
        _P.BOOKINGS_READ, _P.BOOKINGS_CREATE, _P.BOOKINGS_MODIFY, _P.BOOKINGS_CANCEL,
        _P.PAYMENTS_READ, _P.PAYMENTS_REFUND,
        _P.CALLS_READ, _P.CALLS_MANAGE, _P.SUPPORT_READ, _P.SUPPORT_MANAGE,
        _P.VAPI_EXECUTE, _P.VAPI_CONFIGURE,
        _P.ADMIN_READ, _P.ADMIN_MANAGE, _P.AUDIT_READ, _P.AUDIT_EXPORT,
    }),
    Role.SUPER_ADMIN: ALL_PERMISSIONS,
}


class UnknownRoleError(ValueError):
    pass


def permissions_for_roles(roles: "list[str] | frozenset[str] | set[str]") -> frozenset[str]:
    """Union of every permission granted by any of `roles`. Raises
    UnknownRoleError for a role name that isn't in the matrix — silently
    ignoring an unrecognized role would be a fail-open bug (§8/§29:
    authorization must fail closed on anything unexpected)."""
    result: set[str] = set()
    for role in roles:
        if role not in ROLE_PERMISSIONS:
            raise UnknownRoleError(f"Unknown role: {role!r}")
        result |= ROLE_PERMISSIONS[role]
    return frozenset(result)


def has_permission(granted: "frozenset[str] | set[str]", required: str) -> bool:
    return required in granted


def has_any_permission(granted: "frozenset[str] | set[str]", required: "list[str]") -> bool:
    return any(r in granted for r in required)


def has_all_permissions(granted: "frozenset[str] | set[str]", required: "list[str]") -> bool:
    return all(r in granted for r in required)
