"""
FastAPI translation layer for the security core (§9).

This file's ONLY job is to turn an HTTP request into a CurrentActor, and
turn an AuthDecision into an HTTP exception. It should contain as little
*logic* as possible — almost everything worth unit testing already has
been, dependency-free, in app/core/security/*.py (93 real, executed
tests — see tests/test_security_core.py). If you're tempted to add an
`if` here that decides ALLOW vs DENY, it almost certainly belongs in
app/core/security/ownership.py instead, where it can be tested without a
database.

THE TRUST BOUNDARY: get_current_actor() is the only place in this
codebase that constructs a CurrentActor from an HTTP request, and it
reads the session cookie — nothing else. It never reads x-user-id,
customerId, or any other client-supplied identity field, because
CurrentActor's constructor has no parameter for one to flow into (see
app/core/security/actor.py's docstring, and
tests/test_security_core.py::CriticalSecurityTest).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from fastapi import Cookie, Depends, Request
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.core.security.actor import ActorType, CurrentActor
from app.core.security.errors import AuthErrorCode
from app.core.security.ownership import (
    authorize_booking_access,
    authorize_customer_profile_access,
    authorize_passenger_access,
    authorize_payment_access,
    authorize_staff_access,
)
from app.core.security.rbac import Permission
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.services.rbac_service import RBACService
from app.services.session_service import SessionService

SESSION_COOKIE_NAME = "c123_session"


# ------------------------------------------------------------ identity


def get_current_actor(
    request: Request,
    db: Session = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> CurrentActor:
    """Never raises — an absent/invalid/expired/revoked session simply
    produces ANONYMOUS_VERIFIED with no verification fields set. Most
    routes are intentionally reachable anonymously (flight search,
    booking lookup with its own verification step, register, login); the
    ones that require a signed-in human use require_authenticated_user
    below, which DOES raise."""
    request_id = getattr(request.state, "request_id", None)

    if not session_token:
        return CurrentActor(actor_type=ActorType.ANONYMOUS_VERIFIED, request_id=request_id)

    session = SessionService(db).validate_session(session_token)
    if session is None:
        return CurrentActor(actor_type=ActorType.ANONYMOUS_VERIFIED, request_id=request_id)

    user = UserRepository(db).get_by_id(session.user_id)
    if user is None or user.deleted_at is not None or user.status == "DISABLED":
        # A session can outlive its user being disabled/deleted between
        # requests (§29: "Suspending a user prevents active sessions from
        # continuing to authorize requests") — fail closed, not open.
        return CurrentActor(actor_type=ActorType.ANONYMOUS_VERIFIED, request_id=request_id)

    rbac = RBACService(db)
    return CurrentActor(
        actor_type=ActorType.HUMAN_USER,
        user_id=str(user.id),
        customer_id=(str(user.customer_id) if user.customer_id else None),
        roles=rbac.roles_for_user(user.id),
        permissions=rbac.permissions_for_user(user.id),
        account_status=user.status,
        request_id=request_id,
    )


def require_authenticated_user(actor: CurrentActor = Depends(get_current_actor)) -> CurrentActor:
    if not actor.is_authenticated_human:
        raise AuthError(AuthErrorCode.AUTHENTICATION_REQUIRED, "Please sign in to continue.")
    if actor.account_status == "SUSPENDED":
        raise AuthError(AuthErrorCode.ACCOUNT_SUSPENDED, "This account is suspended. Contact support for help.")
    return actor


def require_permission(permission: str) -> Callable[..., CurrentActor]:
    def _dependency(actor: CurrentActor = Depends(require_authenticated_user)) -> CurrentActor:
        if not actor.has_permission(permission):
            raise AuthError(AuthErrorCode.PERMISSION_DENIED, "You don't have permission to do that.")
        return actor

    return _dependency


def require_staff_permission(permission: str) -> Callable[..., CurrentActor]:
    """Phase 9 (T-6) — for admin-dashboard LIST/overview endpoints that
    are not scoped to one resource's owner (list-all-customers,
    list-all-calls, list-all-bookings, analytics). See
    app/core/security/ownership.py::authorize_staff_access's docstring
    for why plain require_permission() is NOT safe to reuse here: some
    permissions (CUSTOMERS_READ in particular) are held by the bare
    CUSTOMER role too, for reading their OWN profile only — this
    dependency additionally requires actor.is_staff so a customer can
    never satisfy an admin-wide list this way.

    A single-resource admin GET (e.g. GET /api/v1/customers/{id}) does
    NOT use this — it uses require_customer_profile_access below, which
    already correctly lets either the owner OR staff through, because it
    has an actual target_customer_id to check ownership against."""

    def _dependency(actor: CurrentActor = Depends(require_authenticated_user)) -> CurrentActor:
        decision = authorize_staff_access(actor, required_permission=permission)
        if not decision.allowed:
            raise AuthError(decision.error_code or AuthErrorCode.FORBIDDEN.value, "You don't have access to do that.")
        return actor

    return _dependency


def require_role(*role_names: str) -> Callable[..., CurrentActor]:
    """Prefer require_permission() — this exists for the rare case §8
    itself calls out (e.g. an admin-only *screen*, not a specific
    mutation). Still requires authentication first; still not "role name
    alone" as the only signal for anything that mutates data."""

    def _dependency(actor: CurrentActor = Depends(require_authenticated_user)) -> CurrentActor:
        if not (actor.roles & set(role_names)):
            raise AuthError(AuthErrorCode.FORBIDDEN, "You don't have access to do that.")
        return actor

    return _dependency


def require_admin(actor: CurrentActor = Depends(require_authenticated_user)) -> CurrentActor:
    if not actor.has_permission(Permission.ADMIN_MANAGE.value):
        raise AuthError(AuthErrorCode.PERMISSION_DENIED, "You don't have permission to do that.")
    return actor


# ------------------------------------------------------------ ownership (§10/§11)
#
# These translate an AuthDecision into an HTTP exception. Route handlers
# call them explicitly, AFTER loading the resource by its own primary
# key/PNR — never via FastAPI's Depends() body-parsing, because the
# resource has to already be loaded from the DB (by server-side truth,
# not a client-claimed id) before there's anything to check ownership
# of. See app/api/routes/bookings.py for the call sites.


def require_customer_profile_access(
    actor: CurrentActor, *, target_customer_id: str, permission: str
) -> CurrentActor:
    decision = authorize_customer_profile_access(
        actor, target_customer_id=target_customer_id, required_permission=permission
    )
    if not decision.allowed:
        raise AuthError(decision.error_code or AuthErrorCode.FORBIDDEN.value, "You don't have access to do that.")
    return actor


def redeem_verification_token(
    actor: CurrentActor,
    *,
    booking,
    verification_purpose: str,
    verification_token: Optional[str],
    db: Session,
) -> CurrentActor:
    """Extracted during Phase 5 — this exact ~13-line block was
    previously duplicated byte-for-byte in require_booking_access and
    require_passenger_access below; app/api/routes/vapi.py's webhook
    handler now calls this too instead of carrying a third copy for
    ActorType.VAPI_AGENT.

    If `actor` is an anonymous web caller OR a Vapi voice caller, and a
    `verification_token` was supplied, this redeems it via
    VerificationSessionService.check() — a valid, correctly-scoped,
    unexpired token upgrades the *effective* actor used for the
    authorization decision. The original `actor` is never mutated;
    CurrentActor is frozen, so this always returns a new instance when it
    upgrades one (see app.core.security.actor).

    Safety of adding VAPI_AGENT to this check (Phase 5): every existing,
    Phase 4-tested call site only ever passes ANONYMOUS_VERIFIED,
    HUMAN_USER, or staff actor types here — for all of those, this
    function's condition evaluates exactly as it did before this change
    (HUMAN_USER/staff already skip this branch entirely, since it only
    ever fired for ANONYMOUS_VERIFIED). VAPI_AGENT is a code path no
    Phase 4 test exercised, because nothing before Phase 5 ever
    constructed a VAPI_AGENT CurrentActor at all. Adding it here cannot
    change the outcome of anything already tested; it only makes a
    previously-impossible call newly possible, which is the entire point.
    """
    if actor.actor_type not in (ActorType.ANONYMOUS_VERIFIED, ActorType.VAPI_AGENT) or not verification_token:
        return actor

    from app.services.verification_service import VerificationSessionService

    redeemed = VerificationSessionService(db).check(
        raw_token=verification_token, booking_id=str(booking.id), purpose=verification_purpose
    )
    if not redeemed:
        return actor
    return replace(
        actor,
        verified_booking_id=str(booking.id),
        verified_purpose=verification_purpose,
        booking_verification_status="VERIFIED",
    )


def require_booking_access(
    actor: CurrentActor,
    *,
    booking,
    required_permission: str,
    verification_purpose: str,
    verification_token: Optional[str] = None,
    db: Session,
) -> CurrentActor:
    """§11's actual enforcement point for booking lookup/modify/cancel.
    Token redemption itself now lives in redeem_verification_token()
    above (Phase 5 extraction) — see that function's docstring."""
    effective_actor = redeem_verification_token(
        actor, booking=booking, verification_purpose=verification_purpose, verification_token=verification_token, db=db
    )

    decision = authorize_booking_access(
        effective_actor,
        booking_customer_id=(str(booking.customer_id) if booking.customer_id else None),
        booking_id=str(booking.id),
        required_permission=required_permission,
        verification_purpose=verification_purpose,
    )
    if not decision.allowed:
        raise AuthError(decision.error_code or AuthErrorCode.FORBIDDEN.value, "You don't have access to do that.")
    return effective_actor


def require_passenger_access(
    actor: CurrentActor,
    *,
    booking,
    required_permission: str,
    verification_purpose: str,
    verification_token: Optional[str] = None,
    db: Session,
) -> CurrentActor:
    """Same shape as require_booking_access — a passenger record's
    ownership is inherited from its booking (§10)."""
    effective_actor = redeem_verification_token(
        actor, booking=booking, verification_purpose=verification_purpose, verification_token=verification_token, db=db
    )

    decision = authorize_passenger_access(
        effective_actor,
        booking_customer_id=(str(booking.customer_id) if booking.customer_id else None),
        booking_id=str(booking.id),
        required_permission=required_permission,
        verification_purpose=verification_purpose,
    )
    if not decision.allowed:
        raise AuthError(decision.error_code or AuthErrorCode.FORBIDDEN.value, "You don't have access to do that.")
    return effective_actor


def require_payment_access(actor: CurrentActor, *, booking, required_permission: str) -> CurrentActor:
    """Phase 6 Milestone 1: called by app/api/routes/payments.py's two
    web routes (create/status). The rule itself (FINANCE/ADMIN or the
    authenticated owner, never a verification token) was written in
    Phase 4, before any payment route existed — see
    authorize_payment_access()'s own docstring and
    tests.test_security_core.PaymentAccessTests for why the Vapi/voice
    path deliberately does NOT go through this function."""
    decision = authorize_payment_access(
        actor,
        booking_customer_id=(str(booking.customer_id) if booking.customer_id else None),
        booking_id=str(booking.id),
        required_permission=required_permission,
    )
    if not decision.allowed:
        raise AuthError(decision.error_code or AuthErrorCode.FORBIDDEN.value, "You don't have access to do that.")
    return actor
