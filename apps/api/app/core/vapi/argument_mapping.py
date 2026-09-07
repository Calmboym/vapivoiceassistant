"""
Vapi tool-call argument mapping (Phase 5).

Deliberately dependency-free (stdlib only) — see package docstring.

Each `map_*` function takes a Vapi tool call's already-parsed `arguments`
dict (see `parse_tool_call_arguments` for turning Vapi's raw payload into
that dict) and returns a plain dict of kwargs shaped EXACTLY like the
corresponding existing Pydantic request schema in app/schemas/, field for
field — e.g. `map_cancel_booking(...)` returns a dict with exactly
BookingCancelRequest's fields. app/api/routes/vapi.py does
`BookingCancelRequest(**map_cancel_booking(args, call_id=call_id))`. This
file never imports Pydantic/FastAPI/SQLAlchemy and never constructs a
schema instance itself, so it stays importable and testable in this
sandbox — Pydantic's own validation (types, EmailStr, length constraints)
still runs when the route layer builds the real schema object; this layer
only checks "are the fields this tool needs even present," and produces a
short, conversational error message when they're not (never a raw
exception — see app/core/exceptions.py's "never leak a stack trace"
rule, which this mirrors for the voice channel).

Idempotency keys are ALWAYS derived here via
app.core.idempotency.derive_idempotency_key(call_id, operation, payload)
— an existing, already-tested Phase 4 function, not new logic — and are
never read from the LLM's arguments even if it supplies one. This is the
concrete mechanism behind every mutating tool schema's "server-derived,
never LLM-supplied" note in tool_schemas.py.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from app.core.idempotency import derive_idempotency_key


class ArgumentMappingError(Exception):
    """Raised for a malformed/incomplete tool call — always a *caller*
    problem (bad arguments), never a server fault. app/api/routes/vapi.py
    catches this and turns it into one `results[].error` string for the
    one offending toolCallId, exactly like AppError subclasses are turned
    into an HTTP response envelope by app/core/exceptions.py — same
    "structured error, no stack trace" discipline, adapted to the shape
    Vapi's webhook contract requires (see that route's module docstring)."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def parse_tool_call_arguments(raw: Any) -> dict:
    """Vapi's documented function-calling shape is OpenAI-style, where
    `function.arguments` is conventionally a JSON-encoded STRING: some
    Vapi client libraries/integrations instead hand callers an
    already-parsed object (observed while researching this phase — Vapi's
    own docs don't pin this down as tightly as the rest of the tool-call
    contract). Handling both defensively costs nothing and avoids a
    fragile assumption in either direction."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ArgumentMappingError("INVALID_ARGUMENTS", "That request wasn't formatted correctly.") from exc
        if not isinstance(parsed, dict):
            raise ArgumentMappingError("INVALID_ARGUMENTS", "That request wasn't formatted correctly.")
        return parsed
    raise ArgumentMappingError("INVALID_ARGUMENTS", "That request wasn't formatted correctly.")


def _require(args: dict, *names: str) -> None:
    missing = [n for n in names if args.get(n) in (None, "")]
    if missing:
        raise ArgumentMappingError(
            "MISSING_ARGUMENT",
            f"I still need {', '.join(missing)} before I can do that.",
        )


def _pnr(args: dict) -> str:
    _require(args, "pnr")
    pnr = str(args["pnr"]).strip().upper()
    if len(pnr) != 6:
        raise ArgumentMappingError("INVALID_ARGUMENTS", "That confirmation number doesn't look right — it should be 6 characters.")
    return pnr


# --- read-only tools ---------------------------------------------------


def map_search_flights(args: dict) -> dict:
    _require(args, "origin", "destination", "departure_date", "adults")
    return {
        "origin": str(args["origin"]).strip().upper(),
        "destination": str(args["destination"]).strip().upper(),
        "departure_date": args["departure_date"],
        "adults": int(args["adults"]),
        "children": int(args.get("children", 0) or 0),
        "infants": int(args.get("infants", 0) or 0),
        "cabin_class": args.get("cabin_class", "economy"),
        "direct_only": bool(args.get("direct_only", False)),
    }


def map_get_flight_details(args: dict) -> dict:
    _require(args, "flight_id")
    return {"flight_id": args["flight_id"]}


def map_get_aircraft_availability(args: dict) -> dict:
    return {
        "origin": (str(args["origin"]).strip().upper() if args.get("origin") else None),
        "category": args.get("category"),
        "on_date": args.get("on_date"),
        "min_seats": (int(args["min_seats"]) if args.get("min_seats") is not None else None),
    }


def map_get_fare_quote(args: dict) -> dict:
    _require(args, "flight_id", "adults")
    return {
        "flight_id": args["flight_id"],
        "adults": int(args["adults"]),
        "children": int(args.get("children", 0) or 0),
        "infants": int(args.get("infants", 0) or 0),
        "cabin_class": args.get("cabin_class", "economy"),
    }


def map_get_cancellation_policy(args: dict) -> dict:
    return {"pnr": _pnr(args)}


def map_get_baggage_policy(args: dict) -> dict:
    _require(args, "cabin_class")
    return {"cabin_class": args["cabin_class"], "aircraft_type": args.get("aircraft_type")}


def map_verify_booking_customer(args: dict) -> dict:
    pnr = _pnr(args)
    if not args.get("email_or_phone") and not args.get("last_name"):
        raise ArgumentMappingError(
            "MISSING_ARGUMENT", "I need either the email or phone on the booking, or a passenger's last name."
        )
    return {
        "pnr": pnr,
        # Hardcoded, never taken from `args` — see module and
        # tool_schemas.py docstrings on why the Vapi channel always
        # verifies for this one fixed purpose.
        "purpose": "vapi_tool_access",
        "verification_token": args.get("verification_token"),
        "email_or_phone": args.get("email_or_phone"),
        "last_name": args.get("last_name"),
    }


def map_get_booking(args: dict) -> dict:
    pnr = _pnr(args)
    _require(args, "verification_token")
    return {"pnr": pnr, "verification_token": args["verification_token"]}


# --- mutating tools: idempotency-key derivation lives here -------------


def map_create_booking(args: dict, *, call_id: str) -> dict:
    _require(args, "quote_id", "passengers", "contact_email", "contact_phone")
    passengers = args["passengers"]
    if not isinstance(passengers, list) or not passengers:
        raise ArgumentMappingError("MISSING_ARGUMENT", "I need at least one passenger's name.")
    mapped_passengers = []
    for p in passengers:
        if not isinstance(p, dict) or not p.get("first_name") or not p.get("last_name"):
            raise ArgumentMappingError("MISSING_ARGUMENT", "Every passenger needs a first and last name.")
        mapped_passengers.append(
            {
                "first_name": p["first_name"],
                "last_name": p["last_name"],
                "date_of_birth": p.get("date_of_birth"),
                "passenger_type": p.get("passenger_type", "adult"),
            }
        )
    payload = {
        "quote_id": args["quote_id"],
        "passengers": mapped_passengers,
        "contact_email": args["contact_email"],
        "contact_phone": args["contact_phone"],
    }
    idempotency_key = derive_idempotency_key(call_id, "create_booking", payload)
    return {
        "quote_id": payload["quote_id"],
        "passengers": mapped_passengers,
        "contact": {"email": payload["contact_email"], "phone": payload["contact_phone"]},
        "idempotency_key": idempotency_key,
    }


def map_modify_booking(args: dict, *, call_id: str) -> dict:
    pnr = _pnr(args)
    _require(args, "verification_token")
    if args.get("customer_confirmed") is not True:
        # Deliberately not part of _require() above: an omitted field and
        # an explicit `false` both mean "not confirmed" and must produce
        # the SAME error code — a caller (LLM) that left the field out
        # entirely shouldn't get a different, less actionable message
        # than one that included it as false. (Caught by
        # tests/test_vapi_core.py during Phase 5 — the first version of
        # this function required customer_confirmed via _require(), which
        # raised MISSING_ARGUMENT instead of CONFIRMATION_REQUIRED when
        # the field was left out.)
        raise ArgumentMappingError(
            "CONFIRMATION_REQUIRED", "This change needs the customer's explicit yes before I can make it."
        )
    if not any(args.get(k) for k in ("new_flight_id", "new_contact_email", "new_contact_phone")):
        raise ArgumentMappingError("MISSING_ARGUMENT", "I need to know what to change — a new flight or new contact details.")
    payload = {
        "pnr": pnr,
        "new_flight_id": args.get("new_flight_id"),
        "new_contact_email": args.get("new_contact_email"),
        "new_contact_phone": args.get("new_contact_phone"),
    }
    idempotency_key = derive_idempotency_key(call_id, "modify_booking", payload)
    return {
        "pnr": pnr,
        "idempotency_key": idempotency_key,
        "customer_confirmed": True,
        "new_flight_id": payload["new_flight_id"],
        "new_contact_email": payload["new_contact_email"],
        "new_contact_phone": payload["new_contact_phone"],
        "verification_token": args["verification_token"],
    }


def map_cancel_booking(args: dict, *, call_id: str) -> dict:
    pnr = _pnr(args)
    _require(args, "verification_token")
    if args.get("customer_confirmed") is not True:
        # See map_modify_booking()'s comment above — same reasoning.
        raise ArgumentMappingError(
            "CONFIRMATION_REQUIRED", "Cancelling needs the customer's explicit yes before I can do it."
        )
    idempotency_key = derive_idempotency_key(call_id, "cancel_booking", {"pnr": pnr})
    return {
        "pnr": pnr,
        "idempotency_key": idempotency_key,
        "customer_confirmed": True,
        "verification_token": args["verification_token"],
    }


def map_add_passenger(args: dict) -> dict:
    pnr = _pnr(args)
    _require(args, "verification_token", "first_name", "last_name")
    return {
        "pnr": pnr,
        "verification_token": args["verification_token"],
        "first_name": args["first_name"],
        "middle_name": args.get("middle_name"),
        "last_name": args["last_name"],
        "date_of_birth": args.get("date_of_birth"),
        "passenger_type": args.get("passenger_type", "adult"),
        "gender": args.get("gender"),
        "nationality": args.get("nationality"),
        "meal_preference": args.get("meal_preference"),
        "seat_preference": args.get("seat_preference"),
        "special_assistance": args.get("special_assistance"),
        "frequent_flyer_number": args.get("frequent_flyer_number"),
    }


def map_remove_passenger(args: dict) -> dict:
    pnr = _pnr(args)
    _require(args, "verification_token", "booking_passenger_id")
    if args.get("customer_confirmed") is not True:
        # PassengerService.remove_passenger() itself has no
        # customer_confirmed check (unlike cancel/modify's service
        # methods) — §11 still calls for confirmation on this tool, so
        # it's enforced here, one layer up, rather than silently
        # skipped. Worth folding into the service method directly in a
        # later phase for consistency — see this phase's handoff, Known
        # Limitations. See map_modify_booking()'s comment on why this
        # check is separate from _require() rather than folded into it.
        raise ArgumentMappingError(
            "CONFIRMATION_REQUIRED", "Removing a passenger needs the customer's explicit yes before I can do it."
        )
    return {
        "pnr": pnr,
        "verification_token": args["verification_token"],
        "booking_passenger_id": args["booking_passenger_id"],
    }


def map_transfer_to_human(args: dict) -> dict:
    return {"reason": args.get("reason") or "not specified"}


# --- Phase 6 Milestone 1: payments (Stripe) -----------------------------


def map_create_payment_session(args: dict, *, call_id: str) -> dict:
    pnr = _pnr(args)
    _require(args, "verification_token")
    if args.get("customer_confirmed") is not True:
        # See map_modify_booking()'s comment above — identical reasoning:
        # an omitted field and an explicit `false` must both raise
        # CONFIRMATION_REQUIRED, never a generic MISSING_ARGUMENT.
        raise ArgumentMappingError(
            "CONFIRMATION_REQUIRED", "Starting a payment needs the customer's explicit yes before I can do it."
        )
    idempotency_key = derive_idempotency_key(call_id, "create_payment_session", {"pnr": pnr})
    return {
        "pnr": pnr,
        "idempotency_key": idempotency_key,
        "customer_confirmed": True,
        "verification_token": args["verification_token"],
    }


def map_get_payment_status(args: dict) -> dict:
    pnr = _pnr(args)
    _require(args, "verification_token")
    return {"pnr": pnr, "verification_token": args["verification_token"]}


TOOL_ARGUMENT_MAPPERS: dict[str, Callable[..., dict]] = {
    "search_flights": map_search_flights,
    "get_flight_details": map_get_flight_details,
    "get_aircraft_availability": map_get_aircraft_availability,
    "get_fare_quote": map_get_fare_quote,
    "get_cancellation_policy": map_get_cancellation_policy,
    "get_baggage_policy": map_get_baggage_policy,
    "verify_booking_customer": map_verify_booking_customer,
    "get_booking": map_get_booking,
    "create_booking": map_create_booking,
    "modify_booking": map_modify_booking,
    "cancel_booking": map_cancel_booking,
    "add_passenger": map_add_passenger,
    "remove_passenger": map_remove_passenger,
    "transfer_to_human": map_transfer_to_human,
    "create_payment_session": map_create_payment_session,
    "get_payment_status": map_get_payment_status,
}

# Tools that call derive_idempotency_key() and therefore need call_id —
# app/api/routes/vapi.py uses this to decide whether to call a mapper as
# `mapper(args)` or `mapper(args, call_id=call_id)`.
MAPPERS_REQUIRING_CALL_ID: frozenset[str] = frozenset(
    {"create_booking", "modify_booking", "cancel_booking", "create_payment_session"}
)
