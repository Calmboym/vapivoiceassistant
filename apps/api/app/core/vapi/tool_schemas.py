"""
Vapi tool JSON schemas (Phase 5 — PROJECT_HANDOFF_PHASE_4.md §10 step 1,
§11's tool table).

Deliberately dependency-free (stdlib only) — see package docstring.

This is tool *shape*: what the LLM sees (name, description, JSON-Schema
parameters) and UX metadata (does it mutate state, does it need an
explicit customer confirmation before executing, is it actually wired to
real backend capability yet). It is NOT authorization policy — that stays
in app/core/security/vapi_authorization.py::TOOL_AUTHORIZATION_MATRIX,
exactly per that file's own docstring ("if you're tempted to add an `if`
here that decides ALLOW vs DENY, it almost certainly belongs in
ownership.py instead"). Keeping the two separate means the security
matrix can be reasoned about (and audited) without wading through JSON
Schema, and this file can be reasoned about (and handed to whoever
configures the Vapi Assistant) without wading through authorization
logic.

`tests/test_vapi_core.py::ToolRegistryConsistencyTests` asserts these two
registries name exactly the same set of tools — a real, executed test
guarding against precisely the kind of drift found while auditing
PROJECT_HANDOFF_PHASE_4.md itself (§9 vs. §11 disagreeing on a tool's
name — see this phase's handoff for the full account).

Every `parameters` dict below is a JSON Schema object, matched field-for-
field against the existing Pydantic request schema it will be adapted
into by argument_mapping.py — e.g. cancel_booking's parameters are
BookingCancelRequest's fields minus `idempotency_key` (server-derived,
never LLM-supplied — see argument_mapping.py's module docstring) and
`pnr`'s length constraint mirrors `Field(..., min_length=6, max_length=6)`
in app/schemas/booking.py. `verify_booking_customer` never exposes
`purpose` as a parameter, on purpose: the Vapi channel always verifies
for the single fixed purpose "vapi_tool_access" (see
vapi_authorization.py's VAPI_ASSISTANT_PERMISSIONS docstring for why),
so letting an LLM pick a `purpose` string would do nothing but create a
confusing parameter that argument_mapping.py would ignore anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class VapiToolSchema:
    name: str
    description: str
    parameters: Mapping[str, Any]  # JSON Schema, `{"type": "object", ...}`
    mutates: bool
    requires_confirmation: bool
    # False for tools registered for shape/authorization completeness but
    # without real backend capability behind them yet (§11: "Not yet
    # modeled", or a Phase 6/7 external integration). argument_mapping.py
    # dispatches these to a fixed "not available yet" result rather than
    # fabricating success — see its `NOT_YET_IMPLEMENTED_TOOLS`.
    implemented: bool = True


def _obj(properties: Mapping[str, Any], required: "list[str]", **extra: Any) -> dict:
    schema = {"type": "object", "properties": dict(properties), "required": list(required)}
    schema.update(extra)
    return schema


_CABIN_CLASS_ENUM = ["economy", "premium_economy", "business", "first", "charter"]
_PASSENGER_TYPE_ENUM = ["adult", "child", "infant"]

# --- read-only / public tools --------------------------------------------

_SEARCH_FLIGHTS = VapiToolSchema(
    name="search_flights",
    description=(
        "Search available flights between two airports on a given date. Use IATA "
        "airport codes if the caller gives one directly; if they name a city, "
        "resolve it first (a city with multiple airports will need the caller to "
        "pick one)."
    ),
    parameters=_obj(
        {
            "origin": {"type": "string", "minLength": 3, "maxLength": 3, "description": "Origin IATA code, e.g. FRA"},
            "destination": {"type": "string", "minLength": 3, "maxLength": 3, "description": "Destination IATA code"},
            "departure_date": {"type": "string", "format": "date", "description": "YYYY-MM-DD"},
            "adults": {"type": "integer", "minimum": 1, "maximum": 20, "default": 1},
            "children": {"type": "integer", "minimum": 0, "maximum": 20, "default": 0},
            "infants": {"type": "integer", "minimum": 0, "maximum": 10, "default": 0},
            "cabin_class": {"type": "string", "enum": _CABIN_CLASS_ENUM, "default": "economy"},
            "direct_only": {"type": "boolean", "default": False},
        },
        required=["origin", "destination", "departure_date", "adults"],
    ),
    mutates=False,
    requires_confirmation=False,
)

_GET_FLIGHT_DETAILS = VapiToolSchema(
    name="get_flight_details",
    description="Get full details for a single flight by its flight_id, as returned by search_flights.",
    parameters=_obj({"flight_id": {"type": "string"}}, required=["flight_id"]),
    mutates=False,
    requires_confirmation=False,
)

_GET_AIRCRAFT_AVAILABILITY = VapiToolSchema(
    name="get_aircraft_availability",
    description="Check charter aircraft availability, optionally filtered by origin, category, date, or minimum seats.",
    parameters=_obj(
        {
            "origin": {"type": "string", "minLength": 3, "maxLength": 3},
            "category": {"type": "string", "enum": ["commercial", "charter"]},
            "on_date": {"type": "string", "format": "date"},
            "min_seats": {"type": "integer", "minimum": 1},
        },
        required=[],
    ),
    mutates=False,
    requires_confirmation=False,
)

_GET_FARE_QUOTE = VapiToolSchema(
    name="get_fare_quote",
    description=(
        "Price a specific flight for a given passenger mix. Returns a quote_id that "
        "create_booking needs — a quote expires, so don't reuse an old one across a "
        "long pause in the conversation."
    ),
    parameters=_obj(
        {
            "flight_id": {"type": "string"},
            "adults": {"type": "integer", "minimum": 1, "maximum": 20, "default": 1},
            "children": {"type": "integer", "minimum": 0, "maximum": 20, "default": 0},
            "infants": {"type": "integer", "minimum": 0, "maximum": 10, "default": 0},
            "cabin_class": {"type": "string", "enum": _CABIN_CLASS_ENUM, "default": "economy"},
        },
        required=["flight_id", "adults"],
    ),
    mutates=False,
    requires_confirmation=False,
)

_GET_CANCELLATION_POLICY = VapiToolSchema(
    name="get_cancellation_policy",
    description="Look up the refund amount and cancellation fee that would apply to a booking, without cancelling it.",
    parameters=_obj({"pnr": {"type": "string", "minLength": 6, "maxLength": 6}}, required=["pnr"]),
    mutates=False,
    requires_confirmation=False,
)

_GET_BAGGAGE_POLICY = VapiToolSchema(
    name="get_baggage_policy",
    description="Look up checked/cabin baggage allowance and extra-bag fee for a cabin class.",
    parameters=_obj(
        {
            "cabin_class": {"type": "string", "enum": _CABIN_CLASS_ENUM},
            "aircraft_type": {"type": "string", "description": "Optional — narrows the answer to a specific aircraft type."},
        },
        required=["cabin_class"],
    ),
    mutates=False,
    requires_confirmation=False,
)

_VERIFY_BOOKING_CUSTOMER = VapiToolSchema(
    name="verify_booking_customer",
    description=(
        "Verify the caller's identity against a booking before doing anything sensitive "
        "with it (looking up details beyond basic status, modifying, cancelling, or "
        "changing passengers). Ask for the confirmation number, then EITHER the email or "
        "phone on the booking OR the last name of a passenger on it — do not ask for all "
        "of them at once. Returns a verification_token: pass that same token to whichever "
        "tool you call next for this booking. If verification fails, you may ask again and "
        "pass the same verification_token back so retries count against one attempt limit; "
        "after several wrong answers the caller will need to be transferred to a human."
    ),
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "email_or_phone": {"type": "string"},
            "last_name": {"type": "string"},
            "verification_token": {
                "type": "string",
                "description": "Only set this when retrying after a wrong answer — pass back the token from the previous attempt.",
            },
        },
        required=["pnr"],
        anyOf=[{"required": ["email_or_phone"]}, {"required": ["last_name"]}],
    ),
    mutates=False,
    requires_confirmation=False,
)

_GET_BOOKING = VapiToolSchema(
    name="get_booking",
    description="Retrieve full details of a booking. Requires a verification_token from a completed verify_booking_customer call.",
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "verification_token": {"type": "string"},
        },
        required=["pnr", "verification_token"],
    ),
    mutates=False,
    requires_confirmation=False,
)

# --- mutating tools --------------------------------------------------------

_CREATE_BOOKING = VapiToolSchema(
    name="create_booking",
    description=(
        "Create a new booking from a fare quote. Before calling this, read back the "
        "full itinerary and total price from the quote and get an explicit yes from "
        "the caller — this call is not reversible by re-asking, only by cancel_booking "
        "afterward, and a cancellation may carry a fee."
    ),
    parameters=_obj(
        {
            "quote_id": {"type": "string", "description": "From a prior get_fare_quote call."},
            "passengers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "date_of_birth": {"type": "string", "format": "date"},
                        "passenger_type": {"type": "string", "enum": _PASSENGER_TYPE_ENUM, "default": "adult"},
                    },
                    "required": ["first_name", "last_name"],
                },
            },
            "contact_email": {"type": "string", "format": "email"},
            "contact_phone": {"type": "string"},
        },
        required=["quote_id", "passengers", "contact_email", "contact_phone"],
    ),
    mutates=True,
    requires_confirmation=True,
)

_MODIFY_BOOKING = VapiToolSchema(
    name="modify_booking",
    description=(
        "Change the flight or contact details on an existing booking. Requires a "
        "verification_token from a completed verify_booking_customer call, and "
        "customer_confirmed must be true — only set that after the caller has "
        "explicitly agreed to the specific change (and any fee) out loud."
    ),
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "verification_token": {"type": "string"},
            "customer_confirmed": {"type": "boolean"},
            "new_flight_id": {"type": "string"},
            "new_contact_email": {"type": "string", "format": "email"},
            "new_contact_phone": {"type": "string"},
        },
        required=["pnr", "verification_token", "customer_confirmed"],
    ),
    mutates=True,
    requires_confirmation=True,
)

_CANCEL_BOOKING = VapiToolSchema(
    name="cancel_booking",
    description=(
        "Cancel a booking. Requires a verification_token from a completed "
        "verify_booking_customer call. Call get_cancellation_policy first, read the "
        "refund amount and fee back to the caller, and only set customer_confirmed "
        "true after they explicitly agree."
    ),
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "verification_token": {"type": "string"},
            "customer_confirmed": {"type": "boolean"},
        },
        required=["pnr", "verification_token", "customer_confirmed"],
    ),
    mutates=True,
    requires_confirmation=True,
)

_ADD_PASSENGER = VapiToolSchema(
    name="add_passenger",
    description="Add a passenger to an existing booking. Requires a verification_token from a completed verify_booking_customer call.",
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "verification_token": {"type": "string"},
            "first_name": {"type": "string"},
            "middle_name": {"type": "string"},
            "last_name": {"type": "string"},
            "date_of_birth": {"type": "string", "format": "date"},
            "passenger_type": {"type": "string", "enum": _PASSENGER_TYPE_ENUM, "default": "adult"},
            "gender": {"type": "string"},
            "nationality": {"type": "string"},
            "meal_preference": {"type": "string"},
            "seat_preference": {"type": "string"},
            "special_assistance": {"type": "string"},
            "frequent_flyer_number": {"type": "string"},
        },
        required=["pnr", "verification_token", "first_name", "last_name"],
    ),
    mutates=True,
    requires_confirmation=False,
)

_REMOVE_PASSENGER = VapiToolSchema(
    name="remove_passenger",
    description=(
        "Remove a passenger from a booking. Requires a verification_token from a "
        "completed verify_booking_customer call, and explicit confirmation — read back "
        "which passenger is being removed before setting customer_confirmed true."
    ),
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "verification_token": {"type": "string"},
            "booking_passenger_id": {"type": "string", "description": "From get_booking's passenger list."},
            "customer_confirmed": {"type": "boolean"},
        },
        required=["pnr", "verification_token", "booking_passenger_id", "customer_confirmed"],
    ),
    mutates=True,
    requires_confirmation=True,
)

_TRANSFER_TO_HUMAN = VapiToolSchema(
    name="transfer_to_human",
    description=(
        "Log that you're escalating to a human agent — use this whenever the caller asks "
        "for a person, verification fails repeatedly, or the request is outside what your "
        "tools can do. This only records the escalation; immediately after calling it, also "
        "call the transfer tool to actually connect the caller — this tool alone does not "
        "move the call."
    ),
    parameters=_obj({"reason": {"type": "string"}}, required=[]),
    mutates=False,
    requires_confirmation=False,
)

# --- registered for authorization/shape completeness, not yet implemented --

_ADD_BAGGAGE = VapiToolSchema(
    name="add_baggage",
    description="Add extra baggage to a booking. Not yet available — say so and offer a human transfer if the caller needs this now.",
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "verification_token": {"type": "string"},
            "bag_count": {"type": "integer", "minimum": 1},
        },
        required=["pnr", "verification_token", "bag_count"],
    ),
    mutates=True,
    requires_confirmation=True,
    implemented=False,
)

_GET_SEAT_OPTIONS = VapiToolSchema(
    name="get_seat_options",
    description="List available seats on a booking's flight. Not yet available.",
    parameters=_obj(
        {"pnr": {"type": "string", "minLength": 6, "maxLength": 6}, "verification_token": {"type": "string"}},
        required=["pnr", "verification_token"],
    ),
    mutates=False,
    requires_confirmation=False,
    implemented=False,
)

_SELECT_SEAT = VapiToolSchema(
    name="select_seat",
    description="Assign a specific seat to a passenger. Not yet available.",
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "verification_token": {"type": "string"},
            "booking_passenger_id": {"type": "string"},
            "seat_number": {"type": "string"},
        },
        required=["pnr", "verification_token", "booking_passenger_id", "seat_number"],
    ),
    mutates=True,
    requires_confirmation=False,
    implemented=False,
)

_CREATE_PAYMENT_SESSION = VapiToolSchema(
    name="create_payment_session",
    description=(
        "Start payment collection for a booking. Requires a verification_token from a "
        "completed verify_booking_customer call. Read the exact total price back to the "
        "caller BEFORE setting customer_confirmed true — this creates a secure Stripe "
        "payment link for that amount; it does NOT take card details over the phone. "
        "Never ask the caller for their card number, CVV, PIN, or a one-time passcode — "
        "if they try to read card details out loud, stop them and explain they'll pay "
        "through Stripe's own secure page instead. This tool only returns the payment "
        "link as data — say that a payment link has been created, but do not tell the "
        "caller it has been sent to them; sending it is not yet available (offer a human "
        "transfer if they need it delivered right now)."
    ),
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "verification_token": {"type": "string"},
            "customer_confirmed": {"type": "boolean"},
        },
        required=["pnr", "verification_token", "customer_confirmed"],
    ),
    mutates=True,
    requires_confirmation=True,
)

_GET_PAYMENT_STATUS = VapiToolSchema(
    name="get_payment_status",
    description="Check whether a booking has been paid. Requires a verification_token from a completed verify_booking_customer call.",
    parameters=_obj(
        {"pnr": {"type": "string", "minLength": 6, "maxLength": 6}, "verification_token": {"type": "string"}},
        required=["pnr", "verification_token"],
    ),
    mutates=False,
    requires_confirmation=False,
)

_CREATE_SUPPORT_TICKET = VapiToolSchema(
    name="create_support_ticket",
    description="Open a support ticket about a booking for a human to follow up on. Not yet available — offer a human transfer instead.",
    parameters=_obj(
        {
            "pnr": {"type": "string", "minLength": 6, "maxLength": 6},
            "verification_token": {"type": "string"},
            "summary": {"type": "string"},
        },
        required=["pnr", "verification_token", "summary"],
    ),
    mutates=True,
    requires_confirmation=False,
    implemented=False,
)

_CREATE_CALLBACK_REQUEST = VapiToolSchema(
    name="create_callback_request",
    description="Request a human agent call the customer back. Not yet available — offer a human transfer instead if they're available now.",
    parameters=_obj(
        {"phone_number": {"type": "string"}, "reason": {"type": "string"}},
        required=["phone_number"],
    ),
    mutates=True,
    requires_confirmation=False,
    implemented=False,
)

VAPI_TOOL_SCHEMAS: dict[str, VapiToolSchema] = {
    t.name: t
    for t in (
        _SEARCH_FLIGHTS, _GET_FLIGHT_DETAILS, _GET_AIRCRAFT_AVAILABILITY, _GET_FARE_QUOTE,
        _GET_CANCELLATION_POLICY, _GET_BAGGAGE_POLICY, _VERIFY_BOOKING_CUSTOMER, _GET_BOOKING,
        _CREATE_BOOKING, _MODIFY_BOOKING, _CANCEL_BOOKING, _ADD_PASSENGER, _REMOVE_PASSENGER,
        _TRANSFER_TO_HUMAN, _ADD_BAGGAGE, _GET_SEAT_OPTIONS, _SELECT_SEAT, _CREATE_PAYMENT_SESSION,
        _GET_PAYMENT_STATUS, _CREATE_SUPPORT_TICKET, _CREATE_CALLBACK_REQUEST,
    )
}


def as_vapi_function_definitions() -> "list[dict]":
    """The exact shape to paste into a Vapi Assistant's `model.tools`
    (OpenAI-style function-calling — see docs/VAPI.md). One entry per
    registered tool, implemented or not: an unimplemented tool still
    needs to exist in the assistant's tool list so the LLM can call it
    and be told "not available yet" rather than hallucinating an answer
    (§13: never let the LLM invent booking information)."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in VAPI_TOOL_SCHEMAS.values()
    ]
