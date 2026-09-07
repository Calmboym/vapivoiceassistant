"""
Resource-ownership authorization (Phase 4 spec §10, §11, §33).

This is the single place that decides "can this actor touch this
resource". Every one of these functions takes the resource's *actual*
owning customer_id/booking_id — values the caller must have already
looked up server-side from the database by an unambiguous key (the
booking's own primary key / PNR) — and an actor built from a validated
session or verification token. None of these functions has a parameter
for a client-claimed customer id, on purpose:

    def authorize_resource_access(actor, *, resource_customer_id, ...):

There is no `requested_customer_id` argument here to forge in the first
place. §10: "Do not implement authorization merely by checking
`booking.customer_id == requested_customer_id`... Instead derive the
actor/customer identity from the authenticated session." Deriving
`resource_customer_id` from the resource row and `actor.customer_id` from
the session, then comparing the two, *is* that pattern — the forgeable
quantity simply doesn't exist as an input.

Deliberately dependency-free (stdlib only). See
tests/test_security_core.py::OwnershipTests and ::CriticalSecurityTest for
the executed proof of the IDOR-prevention property, including the exact
Customer-A/Customer-B/forged-header scenario from Phase 4 spec §33.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.security.actor import ActorType, CurrentActor


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    reason: str
    error_code: Optional[str] = None  # an AuthErrorCode value when allowed=False

    def __bool__(self) -> bool:
        return self.allowed


def _allow(reason: str) -> AuthDecision:
    return AuthDecision(True, reason)


def _deny(reason: str, error_code: str) -> AuthDecision:
    return AuthDecision(False, reason, error_code)


def authorize_resource_access(
    actor: CurrentActor,
    *,
    resource_customer_id: Optional[str],
    staff_permission: str,
    resource_booking_id: Optional[str] = None,
    verification_purpose: Optional[str] = None,
) -> AuthDecision:
    """The one authorization engine every resource-specific helper below
    calls into. See module docstring for the trust model.

    Priority order (§11 — PUBLIC / AUTHENTICATED CUSTOMER / VERIFIED
    BOOKING / STAFF / ADMIN access are distinct concepts):
      1. Staff/admin: an authenticated human holding `staff_permission`.
         (ADMIN/SUPER_ADMIN simply hold every permission — see rbac.py —
         so this one check covers staff *and* admin access.)
      2. Authenticated owner: a HUMAN_USER whose *session-derived*
         customer_id matches the resource's actual customer_id.
      3. Verified booking access: an ANONYMOUS_VERIFIED or VAPI_AGENT
         actor holding a live, correctly-scoped verification for this
         exact booking_id + purpose (§12).
      4. Otherwise: denied.
    """
    if actor.actor_type == ActorType.HUMAN_USER:
        is_owner = (
            actor.customer_id is not None
            and resource_customer_id is not None
            and actor.customer_id == resource_customer_id
        )
        if is_owner:
            # BUG THIS ORDERING FIXES (found by CriticalSecurityTest, not
            # by inspection): bookings.read/bookings.cancel/etc. are held
            # by the bare CUSTOMER role too (see ROLE_PERMISSIONS) — a
            # customer needs that permission to act on their OWN
            # bookings. If the staff check below ran first and only
            # tested "does this actor hold `staff_permission` at all",
            # ANY customer would pass it for ANY OTHER customer's
            # booking too, since the permission string is identical for
            # both scopes. Checking ownership first, and gating the
            # non-owner path on `is_staff` (a role outside plain
            # CUSTOMER) as well as the permission, is what actually
            # closes that hole — see the code comment on `is_staff` in
            # actor.py for why this still isn't "authorize on role name
            # alone" (§8): both the role-derived scope AND the explicit
            # permission are required.
            if actor.has_permission(staff_permission):
                return _allow("owner")
            return _deny("missing_permission_for_self_access", "PERMISSION_DENIED")

        # Not the resource owner: only reachable by a genuinely *staff*
        # role (anything beyond bare CUSTOMER) holding the specific
        # permission — never by permission-string membership alone.
        if actor.is_staff and actor.has_permission(staff_permission):
            return _allow("staff_permission")
        return _deny("not_owner_not_staff", "FORBIDDEN")

    if actor.actor_type in (ActorType.ANONYMOUS_VERIFIED, ActorType.VAPI_AGENT):
        if (
            verification_purpose is not None
            and resource_booking_id is not None
            and actor.has_valid_booking_verification(resource_booking_id, verification_purpose)
        ):
            if actor.actor_type == ActorType.VAPI_AGENT and not (
                actor.vapi_authenticated and actor.has_permission("vapi.execute")
            ):
                # Held a verification token but the *call itself* was
                # never authenticated as a real Vapi request — §13/§34.
                return _deny("vapi_call_not_authenticated", "AUTHENTICATION_REQUIRED")
            return _allow("verified_booking_token")
        return _deny("no_valid_booking_verification", "BOOKING_VERIFICATION_REQUIRED")

    return _deny("not_owner_not_staff", "FORBIDDEN")


def authorize_booking_access(
    actor: CurrentActor,
    *,
    booking_customer_id: Optional[str],
    booking_id: str,
    required_permission: str,
    verification_purpose: Optional[str] = None,
) -> AuthDecision:
    return authorize_resource_access(
        actor,
        resource_customer_id=booking_customer_id,
        resource_booking_id=booking_id,
        staff_permission=required_permission,
        verification_purpose=verification_purpose,
    )


def authorize_passenger_access(
    actor: CurrentActor,
    *,
    booking_customer_id: Optional[str],
    booking_id: str,
    required_permission: str,
    verification_purpose: Optional[str] = None,
) -> AuthDecision:
    """A passenger record's ownership is inherited from the booking it
    belongs to — there's no separate passenger-level owner (§10: Customer
    B's passenger records must be unreachable to Customer A)."""
    return authorize_resource_access(
        actor,
        resource_customer_id=booking_customer_id,
        resource_booking_id=booking_id,
        staff_permission=required_permission,
        verification_purpose=verification_purpose,
    )


def authorize_customer_profile_access(
    actor: CurrentActor,
    *,
    target_customer_id: Optional[str],
    required_permission: str,
) -> AuthDecision:
    """A customer's own contact/profile info. No verification-token path
    here on purpose — a booking-verification token authorizes acting on
    *that one booking*, not browsing the customer's whole profile."""
    return authorize_resource_access(
        actor,
        resource_customer_id=target_customer_id,
        staff_permission=required_permission,
    )


def authorize_payment_access(
    actor: CurrentActor,
    *,
    booking_customer_id: Optional[str],
    booking_id: str,
    required_permission: str,
) -> AuthDecision:
    """Payments (Phase 6 Milestone 1) never accept a verification-token
    path — no `verification_purpose` parameter exists to pass one. Refunds
    and payment history require either the authenticated owner or explicit
    FINANCE/ADMIN permission, full stop (§14: refund_payment -> FINANCE
    or ADMIN only). This same "no token path" property is what
    create_payment_session/get_payment_status's WEB route relies on
    (app/api/deps_auth.py::require_payment_access) — the Vapi/voice
    equivalents deliberately do NOT call this function at all; see
    docs/PAYMENTS.md "Authorization" and
    tests.test_security_core.PaymentAccessTests."""
    return authorize_resource_access(
        actor,
        resource_customer_id=booking_customer_id,
        resource_booking_id=booking_id,
        staff_permission=required_permission,
    )
