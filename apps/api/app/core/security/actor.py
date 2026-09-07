"""
CurrentActor — the one, single representation of "who is making this
request" that every authorization decision in this codebase is made
against (Phase 4 spec §2, §9, §13).

Deliberately dependency-free (stdlib only) so the entire authorization
core (this file + ownership.py + rbac.py) is unit-testable without
FastAPI/SQLAlchemy — see tests/test_security_core.py.

THIS IS THE TRUST BOUNDARY. A CurrentActor must only ever be constructed
from server-side truth:
  * HUMAN_USER  — from a validated session row looked up by the *hashed*
    session cookie (see app/api/deps.py::get_current_actor). Its
    `user_id` / `customer_id` / `roles` come from that DB row, never from
    any request body, query param, or header the client sent.
  * VAPI_AGENT  — from a Vapi webhook/tool request whose signature has
    already been verified (Phase 5). Its `verified_booking_id` /
    `booking_verification_status` come from a VerificationSession row
    looked up server-side, never from what the LLM claims in its tool
    call arguments (§13: "The LLM must NEVER be treated as an
    administrator").
  * ANONYMOUS_VERIFIED — someone with no account who redeemed a
    short-lived booking-verification token (§12). Scoped to exactly one
    booking_id + purpose.
  * SYSTEM — internal jobs/scripts (seeding, background workers). Never
    constructed from anything HTTP-request-shaped.

No constructor here accepts a "requested customer id" / "x-user-id"-style
argument, on purpose — see ownership.py's docstring and
tests/test_security_core.py::CriticalSecurityTest for what this
specifically prevents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActorType(str, Enum):
    HUMAN_USER = "human_user"
    VAPI_AGENT = "vapi_agent"
    ANONYMOUS_VERIFIED = "anonymous_verified"
    SYSTEM = "system"


@dataclass(frozen=True)
class CurrentActor:
    actor_type: ActorType

    # --- HUMAN_USER fields ---------------------------------------------
    user_id: Optional[str] = None
    customer_id: Optional[str] = None  # the Customer row this actor owns, if any
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    account_status: Optional[str] = None

    # --- VAPI_AGENT fields (§13) -----------------------------------------
    vapi_authenticated: bool = False
    call_id: Optional[str] = None
    assistant_id: Optional[str] = None
    tool_execution_id: Optional[str] = None

    # --- shared: booking-verification scope (§12), used by VAPI_AGENT and
    # ANONYMOUS_VERIFIED alike -------------------------------------------
    verified_booking_id: Optional[str] = None
    verified_purpose: Optional[str] = None
    booking_verification_status: Optional[str] = None  # "VERIFIED" | others

    # --- correlation (§26) -----------------------------------------------
    request_id: Optional[str] = None

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def has_any_permission(self, permissions: "list[str]") -> bool:
        return any(p in self.permissions for p in permissions)

    @property
    def is_authenticated_human(self) -> bool:
        return self.actor_type == ActorType.HUMAN_USER and self.user_id is not None

    @property
    def is_staff(self) -> bool:
        """'Staff' = any authenticated human with at least one non-customer
        permission. Used for coarse UI/UX decisions only — every real
        authorization decision still checks a specific permission, not
        this flag (§8)."""
        if not self.is_authenticated_human:
            return False
        from app.core.security.rbac import ROLE_PERMISSIONS, Role

        return bool(self.roles - {Role.CUSTOMER.value})

    def has_valid_booking_verification(self, booking_id: str, purpose: str) -> bool:
        return (
            self.verified_booking_id == booking_id
            and self.verified_purpose == purpose
            and self.booking_verification_status == "VERIFIED"
        )


SYSTEM_ACTOR = CurrentActor(actor_type=ActorType.SYSTEM, permissions=frozenset({"system.manage"}))
