"""
Vapi tool-call authorization matrix (Phase 4 spec §13, §14, §34).

This is preparation, not the live integration — no Vapi webhook or tool
endpoint is wired up in this phase (that's Phase 5). What's built here is
the *authorization policy* those endpoints will call into, so it exists,
is tested, and is architecturally load-bearing before a single line of
Vapi-specific networking code is written. §13: "The LLM must NEVER be
treated as an administrator. The Vapi agent can only perform operations
allowed by the backend."

Deliberately dependency-free (stdlib only) — reuses CurrentActor /
AuthDecision from actor.py / ownership.py so a real Vapi tool-call handler
in Phase 5 has nothing new to learn: it builds a CurrentActor(actor_type=
VAPI_AGENT, ...) from a signature-verified webhook payload and calls
`authorize_vapi_tool_call()` exactly like a booking route calls
`authorize_booking_access()`.
"""

from __future__ import annotations

from enum import Enum

from app.core.security.actor import ActorType, CurrentActor
from app.core.security.ownership import AuthDecision, authorize_booking_access


class ToolSensitivity(str, Enum):
    PUBLIC = "public"                              # no verification needed
    REQUIRES_VERIFIED_BOOKING = "requires_verified_booking"
    STAFF_OR_ADMIN_ONLY = "staff_or_admin_only"     # never allowed for a bare voice agent


# §14's example authorization matrix, encoded. `permission` is checked
# alongside sensitivity for REQUIRES_VERIFIED_BOOKING tools so a verified
# caller still can't invoke a tool the Vapi assistant itself hasn't been
# scoped to use (defense in depth beyond just "is this booking verified").
#
# Phase 5 extension (PROJECT_HANDOFF_PHASE_4.md §11's full tool list): the
# original 8 entries below this comment are Phase 4, executed and tested
# by VapiAuthorizationTests — left byte-for-byte unchanged. Everything
# after them is new. Three tools from §11 are deliberately NOT registered
# here at all: send_confirmation / send_sms / send_email are system-
# triggered side effects (fired by a service after a state change, e.g.
# after booking.created), never an action the LLM should be choosing to
# invoke — giving them a tool-call entry at all would invite exactly the
# "LLM decides to send an email" failure mode §13 warns about. If that
# changes later, add them here as STAFF_OR_ADMIN_ONLY, matching
# refund_payment/configure_assistant.
TOOL_AUTHORIZATION_MATRIX: dict[str, dict[str, str]] = {
    "search_flights": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "flights.read"},
    "get_flight_details": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "flights.read"},
    "get_booking": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "bookings.read"},
    "modify_booking": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "bookings.modify"},
    "cancel_booking": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "bookings.cancel"},
    "add_passenger": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "passengers.manage"},
    "refund_payment": {"sensitivity": ToolSensitivity.STAFF_OR_ADMIN_ONLY, "permission": "payments.refund"},
    "configure_assistant": {"sensitivity": ToolSensitivity.STAFF_OR_ADMIN_ONLY, "permission": "vapi.configure"},
    # --- Phase 5: read-only / public tools (no booking context needed) ---
    "get_aircraft_availability": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "flights.read"},
    "get_fare_quote": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "flights.read"},
    "get_cancellation_policy": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "bookings.read"},
    "get_baggage_policy": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "flights.read"},
    # verify_booking_customer is what *produces* a verified-booking grant —
    # it cannot itself require one (§11: "Public (it's what produces
    # verification)"). It still requires bookings.read so a Vapi deployment
    # scoped away from bookings entirely can't use it as a PNR-guessing
    # oracle dressed up as "verification."
    "verify_booking_customer": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "bookings.read"},
    # create_booking is PUBLIC in the same sense: there is no pre-existing
    # owner to verify against yet (§11). Idempotency (derive_idempotency_key)
    # is what makes an LLM-retried create_booking call safe, not booking
    # verification.
    "create_booking": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "bookings.create"},
    "transfer_to_human": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "support.read"},
    # --- Phase 5: require an already-verified booking ---
    "remove_passenger": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "passengers.manage"},
    # --- Phase 5: registered for schema/authorization completeness, but
    # backend capability was genuinely absent at the time (§11: "Not yet
    # modeled"). argument_mapping.py's dispatch for these returns an
    # explicit "not available yet" result rather than fabricating
    # success — see app/core/vapi/tool_schemas.py's `implemented` flag.
    "add_baggage": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "passengers.manage"},
    "get_seat_options": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "bookings.read"},
    "select_seat": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "bookings.modify"},
    # Phase 6 Milestone 1: create_payment_session/get_payment_status are
    # now implemented=True in tool_schemas.py — these two entries are
    # UNCHANGED from Phase 5 (sensitivity/permission were already
    # correct before any payment backend existed; see docs/PAYMENTS.md
    # "Authorization" for why this REQUIRES_VERIFIED_BOOKING gate — the
    # same one cancel_booking/modify_booking use — is deliberately kept
    # distinct from authorize_payment_access()'s stricter, verification-
    # token-free web/staff gate rather than merged with it).
    "create_payment_session": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "payments.create"},
    "get_payment_status": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "payments.read"},
    "create_support_ticket": {"sensitivity": ToolSensitivity.REQUIRES_VERIFIED_BOOKING, "permission": "support.read"},
    "create_callback_request": {"sensitivity": ToolSensitivity.PUBLIC, "permission": "support.read"},
}

# The fixed upper bound on what ANY Vapi voice-assistant actor may ever be
# granted, regardless of which tools a given assistant deployment has
# attached in the Vapi dashboard. This is what app/api/routes/vapi.py's
# webhook handler assigns when constructing CurrentActor(actor_type=
# VAPI_AGENT, ...) — see that file's module docstring for why this exists
# as an explicit constant rather than being derived from RBAC roles like a
# HUMAN_USER's permissions are.
#
# Resolves a real ambiguity found while building Phase 5: §9 of
# PROJECT_HANDOFF_PHASE_4.md states a VAPI_AGENT's permission set "is
# always exactly {'vapi.execute'}, by construction" — but
# TOOL_AUTHORIZATION_MATRIX above requires tool-specific permissions
# (flights.read, bookings.cancel, ...), and VapiAuthorizationTests'
# _vapi_actor() test helper already grants a broader set by default. If a
# real VAPI_AGENT actor only ever held {"vapi.execute"}, every
# `actor.has_permission(required_permission)` check in
# authorize_vapi_tool_call() would be unreachable dead logic — every
# sensitivity-gated tool would 403 unconditionally. No code before Phase 5
# actually constructed a VAPI_AGENT CurrentActor (confirmed by grep), so
# this was genuinely undecided, not a contradiction to route around.
#
# The property §9 is actually protecting — a voice agent can never act as
# staff or admin — is preserved here structurally: this set is built from
# TOOL_AUTHORIZATION_MATRIX's own non-STAFF_OR_ADMIN_ONLY permissions plus
# "vapi.execute" itself, so it can never silently pick up a staff/admin
# permission just because a future tool entry is added carelessly above —
# only STAFF_OR_ADMIN_ONLY entries are excluded, and refund_payment /
# configure_assistant (payments.refund / vapi.configure) prove that
# exclusion works (see VapiAuthorizationTests.
# test_staff_only_tool_always_denied_for_vapi_even_with_permission, which
# passes an actor that explicitly HOLDS payments.refund and is still
# denied — sensitivity is checked before permission, so this constant
# being "too broad" on paper is not itself a privilege-escalation path).
VAPI_ASSISTANT_PERMISSIONS: frozenset[str] = frozenset(
    {"vapi.execute"}
    | {
        entry["permission"]
        for entry in TOOL_AUTHORIZATION_MATRIX.values()
        if entry["sensitivity"] != ToolSensitivity.STAFF_OR_ADMIN_ONLY
    }
)


def authorize_vapi_tool_call(
    actor: CurrentActor,
    *,
    tool_name: str,
    booking_id: str | None = None,
    booking_customer_id: str | None = None,
) -> AuthDecision:
    if actor.actor_type != ActorType.VAPI_AGENT:
        return AuthDecision(False, "not_a_vapi_actor", "AUTHENTICATION_REQUIRED")

    # §13: a Vapi request must itself be authenticated (signed webhook /
    # verified tool-call context) before any tool policy is even
    # consulted — this is independent of whether the *booking* has been
    # verified with the customer.
    if not actor.vapi_authenticated:
        return AuthDecision(False, "vapi_call_not_authenticated", "AUTHENTICATION_REQUIRED")

    entry = TOOL_AUTHORIZATION_MATRIX.get(tool_name)
    if entry is None:
        return AuthDecision(False, "unknown_tool", "FORBIDDEN")

    sensitivity = entry["sensitivity"]
    required_permission = entry["permission"]

    if sensitivity == ToolSensitivity.STAFF_OR_ADMIN_ONLY:
        # A voice agent is never staff or admin (§13) — this branch always
        # denies for a VAPI_AGENT actor, regardless of what permissions
        # someone might mistakenly attach to a Vapi credential. Escalation
        # to a human is the only path for these tools.
        return AuthDecision(False, "requires_human_staff_or_admin", "PERMISSION_DENIED")

    if not actor.has_permission(required_permission):
        return AuthDecision(False, "tool_not_permitted_for_this_assistant", "PERMISSION_DENIED")

    if sensitivity == ToolSensitivity.PUBLIC:
        return AuthDecision(True, "public_tool")

    # REQUIRES_VERIFIED_BOOKING
    if booking_id is None:
        return AuthDecision(False, "tool_requires_a_booking_id", "BOOKING_VERIFICATION_REQUIRED")

    return authorize_booking_access(
        actor,
        booking_customer_id=booking_customer_id,
        booking_id=booking_id,
        required_permission=required_permission,
        verification_purpose="vapi_tool_access",
    )
