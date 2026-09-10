"""
Vapi webhook route (Phase 5 — PROJECT_HANDOFF_PHASE_4.md §9/§10/§13).

THIS FILE, LIKE THE REST OF app/api/routes/*.py, IS UNEXECUTED IN THIS
SANDBOX. FastAPI/SQLAlchemy are not importable here (no network access to
install them — see this phase's handoff, Environment & Infrastructure).
It has been written and reviewed against the exact method signatures of
every service/repository/security function it calls (re-verified against
the actual source, not from memory, while building this phase), and it
follows the same request/authorization pattern already executed and
proven by app/api/routes/bookings.py — but "matches an established,
correct pattern" is not the same claim as "was run." Do not represent
this file as tested until it has actually been exercised against a real
FastAPI TestClient + a test database, which needs the full stack this
sandbox doesn't have.

--- The contract this route implements (verified against docs.vapi.ai
    while building this phase, not assumed from training data) ---

Vapi POSTs here for `message.type == "tool-calls"`:
    {"message": {"type": "tool-calls", "toolCallList": [
        {"id": "<toolCallId>", "type": "function",
         "function": {"name": "cancel_booking", "arguments": {...}}}
    ], "call": {"id": "...", "assistantId": "..."}, ...}}

The response MUST be HTTP 200 — Vapi ignores any other status code
entirely — with:
    {"results": [{"toolCallId": "<id>", "result": "<string>"}]}
or, for a tool-specific failure:
    {"results": [{"toolCallId": "<id>", "error": "<string>"}]}
`result`/`error` must be plain strings (Vapi's own troubleshooting docs
call this out explicitly), which is why every dispatch function below
returns a short, speakable sentence, not a JSON object.

The ONE exception to "always 200" is the webhook secret check itself —
see verify_webhook_request()'s call site below. That's not a tool-call
failure, it's "this request did not come from Vapi at all," which is a
different, HTTP-appropriate kind of rejection (§13's outer trust
boundary — see app/core/security/vapi_webhook_auth.py's docstring).

--- The architecture this route enforces (§9/§13/§20) ---

Vapi is the conversation layer, never the source of truth or the
authorization layer. Every tool call below follows the exact same shape:
  1. Parse arguments (app.core.vapi.argument_mapping) — server-side
     parsing, not trusting the LLM's JSON to already be well-formed.
  2. If the tool needs a booking, load it BY PNR FROM THE DATABASE
     (BookingRepository.get_by_pnr) — never trust a client/LLM-supplied
     booking id, only ever a PNR looked up fresh, same rule
     app/api/routes/bookings.py already follows.
  3. If a verification_token was supplied, redeem it server-side
     (_redeem_verification_token below — see its docstring for why this
     isn't simply require_booking_access() reused as-is).
  4. Call authorize_vapi_tool_call() — the ONE authorization gate,
     already built and tested in Phase 4. This is the actual security
     boundary; nothing above it is optional or advisory.
  5. Only then call the SAME application service a web request would
     use (BookingService, CancellationService, PassengerService,
     FlightService) — never reimplemented business logic, per §20 "Vapi
     tools must call the same application services used by the
     web/API layer."
  6. Record a ToolExecution row either way (denied or allowed) — the new
     "tool execution model" this phase was asked to identify (there
     wasn't one before this file).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_airline_provider, get_idempotency_store, get_payment_provider
from app.api.deps_auth import redeem_verification_token
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security.actor import ActorType, CurrentActor
from app.core.security.rate_limiter import BackoffLockout, build_rate_limiter
from app.core.security.redaction import redact_value
from app.core.security.vapi_authorization import VAPI_ASSISTANT_PERMISSIONS, authorize_vapi_tool_call
from app.core.security.vapi_webhook_auth import verify_webhook_request
from app.core.vapi.argument_mapping import (
    MAPPERS_REQUIRING_CALL_ID,
    TOOL_ARGUMENT_MAPPERS,
    ArgumentMappingError,
    parse_tool_call_arguments,
)
from app.core.vapi.rate_limiting import tool_rate_limit_key, webhook_rate_limit_key
from app.core.vapi.tool_schemas import VAPI_TOOL_SCHEMAS
from app.db.session import get_db
from app.models.call import Call
from app.models.tool_execution import ToolExecution
from app.providers.airline.base import ProviderError
from app.providers.payments.base import PaymentProviderError
from app.repositories.booking_repository import BookingRepository
from app.repositories.call_repository import CallRepository
from app.repositories.tool_execution_repository import ToolExecutionRepository
from app.schemas.booking import BookingCancelRequest, BookingCreateRequest, BookingModifyRequest
from app.schemas.passenger import ContactInfo, PassengerCreate
from app.schemas.payment import PaymentSessionCreateRequest
from app.services.booking_service import BookingService
from app.services.cancellation_service import CancellationService
from app.services.email_provider import get_email_provider
from app.services.flight_service import FlightService
from app.services.notification_service import NotificationService
from app.services.passenger_service import PassengerService
from app.services.payment_service import PaymentService
from app.services.rate_limit_service import RedisRateLimitStore
from app.services.sms_provider import get_sms_provider
from app.services.verification_service import VerificationSessionService

router = APIRouter(prefix="/api/v1/vapi", tags=["vapi"])

NOT_YET_AVAILABLE_MESSAGE = (
    "That's not available yet — I can transfer you to a team member who can help with that."
)

# AuthDecision.error_code -> what the assistant should say. Deliberately
# generic/non-diagnostic (never "here's exactly why," which would coach
# an adversarial caller on the boundary — same reasoning as
# app/core/security/errors.py's HTTP-facing messages).
_AUTH_DENIAL_MESSAGES: dict[str, str] = {
    "AUTHENTICATION_REQUIRED": "I wasn't able to authenticate that request.",
    "BOOKING_VERIFICATION_REQUIRED": "I need to verify the booking first — could you give me the confirmation number and either the email or phone on the booking, or a passenger's last name?",
    "PERMISSION_DENIED": "I'm not able to do that.",
    "FORBIDDEN": "I'm not able to do that.",
}
_DEFAULT_DENIAL_MESSAGE = "I'm not able to do that."


def _webhook_rate_limiter():
    # A fresh RedisRateLimitStore() per call is intentional and cheap —
    # it just wraps whatever app.db.redis_client.get_redis() returns
    # (itself process-cached) — same pattern as routes/auth.py's
    # _lockout(), reused here rather than re-derived.
    return build_rate_limiter("vapi_webhook", RedisRateLimitStore())


def _tool_rate_limiter():
    return build_rate_limiter("vapi_tool", RedisRateLimitStore())


def _verification_lockout() -> BackoffLockout:
    return BackoffLockout(RedisRateLimitStore())


# --------------------------------------------------------------------- actor


def _base_vapi_actor(*, call_id: str, assistant_id: Optional[str], tool_execution_id: str) -> CurrentActor:
    return CurrentActor(
        actor_type=ActorType.VAPI_AGENT,
        vapi_authenticated=True,
        call_id=call_id,
        assistant_id=assistant_id,
        tool_execution_id=tool_execution_id,
        permissions=VAPI_ASSISTANT_PERMISSIONS,
    )


def _redeem_verification_token(
    actor: CurrentActor, *, booking, verification_token: Optional[str], db: Session
) -> CurrentActor:
    """Thin wrapper around the shared app.api.deps_auth.
    redeem_verification_token() (Phase 5 extraction — see that
    function's docstring for the full reasoning). Kept as a local
    one-liner rather than calling the shared function directly at each
    of this file's call sites so `purpose` stays pinned to the one fixed
    value the Vapi channel always uses — see
    vapi_authorization.py::VAPI_ASSISTANT_PERMISSIONS docstring — without
    repeating that literal string everywhere."""
    return redeem_verification_token(
        actor, booking=booking, verification_purpose="vapi_tool_access", verification_token=verification_token, db=db
    )


# --------------------------------------------------------------------- call tracking


def _get_or_create_call(db: Session, *, vapi_call_id: str, assistant_id: Optional[str], raw_call: dict) -> Call:
    repo = CallRepository(db)
    call = repo.get_by_vapi_call_id(vapi_call_id)
    if call is not None:
        return call
    phone = raw_call.get("customer", {}) if isinstance(raw_call.get("customer"), dict) else {}
    call = Call(
        vapi_call_id=vapi_call_id,
        assistant_id=assistant_id,
        phone_number_id=raw_call.get("phoneNumberId"),
        direction=raw_call.get("type"),  # Vapi's Call object uses "type" for inbound/outboundPhoneCall etc.
        customer_phone_number=phone.get("number"),
        status="in_progress",
    )
    return repo.add(call)


# --------------------------------------------------------------------- result shaping


def _ok(tool_call_id: str, result: str) -> dict:
    return {"toolCallId": tool_call_id, "result": result}


def _err(tool_call_id: str, message: str) -> dict:
    return {"toolCallId": tool_call_id, "error": message}


def _booking_summary(booking) -> str:
    passenger_count = len(booking.passengers)
    return (
        f"Booking {booking.pnr}: {booking.origin} to {booking.destination}, "
        f"flight {booking.flight_number}, departing {booking.departure_time.isoformat()}, "
        f"status {booking.status}, {passenger_count} passenger(s), "
        f"total {booking.total_price} {booking.currency}."
    )


# --------------------------------------------------------------------- per-tool dispatch
#
# Each function: (mapped_args, *, db, actor, call_id) -> str. Raises
# ArgumentMappingError (bad input), AppError/ProviderError (a real
# business-rule failure, e.g. FlightNotFoundError, NO_CHANGES_SPECIFIED),
# or lets an unexpected exception propagate — the webhook handler's outer
# try/except turns ALL of these into one clean results[].error string, so
# no dispatch function needs its own try/except.


def _dispatch_search_flights(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    offers = FlightService(get_airline_provider()).search(**args)
    if not offers:
        return "No flights matched that search."
    lines = [
        f"{o.flight_number}: {o.origin} to {o.destination}, departs {o.departure_time.isoformat()}, "
        f"{o.price_per_passenger} {o.currency} per passenger, flight_id {o.flight_id}"
        for o in offers[:5]
    ]
    more = f" ({len(offers) - 5} more available)" if len(offers) > 5 else ""
    return "Found these flights: " + "; ".join(lines) + more + "."


def _dispatch_get_flight_details(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    offer = FlightService(get_airline_provider()).get_flight(args["flight_id"])
    return (
        f"Flight {offer.flight_number}: {offer.origin} to {offer.destination}, "
        f"departs {offer.departure_time.isoformat()}, arrives {offer.arrival_time.isoformat()}, "
        f"aircraft {offer.aircraft.aircraft_type}, {offer.price_per_passenger} {offer.currency} per passenger, "
        f"{offer.available_seats} seats available."
    )


def _dispatch_get_aircraft_availability(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    aircraft = FlightService(get_airline_provider()).aircraft_availability(**args)
    if not aircraft:
        return "No aircraft matched that search."
    lines = [f"{a.aircraft_type} ({a.registration}), {a.available_seats} seats, at {a.current_location}" for a in aircraft[:5]]
    return "Available aircraft: " + "; ".join(lines) + "."


def _dispatch_get_fare_quote(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    quote = FlightService(get_airline_provider()).quote(**args)
    return (
        f"Quote {quote.quote_id}: {quote.total_price} {quote.currency} total for this itinerary, "
        f"valid until {quote.expires_at.isoformat()}."
    )


def _dispatch_get_cancellation_policy(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    service = CancellationService(db, get_airline_provider(), get_idempotency_store(), get_payment_provider())
    booking, policy = service.get_policy(args["pnr"])
    if policy.already_cancelled:
        return f"Booking {booking.pnr} is already cancelled."
    return (
        f"Cancelling booking {booking.pnr} now would refund {policy.refundable_amount} {policy.currency} "
        f"and charge a {policy.cancellation_fee} {policy.currency} cancellation fee."
    )


def _dispatch_get_baggage_policy(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    rules = FlightService(get_airline_provider()).baggage_rules(args["cabin_class"], args.get("aircraft_type"))
    return (
        f"{rules.checked_bags_included} checked bag(s) included, up to {rules.checked_bag_max_kg}kg each, "
        f"cabin bag up to {rules.cabin_bag_max_kg}kg. Extra bags are {rules.extra_bag_fee} {rules.currency} each."
    )


def _dispatch_verify_booking_customer(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    booking = BookingRepository(db).get_by_pnr(args["pnr"])
    if booking is None:
        return "I couldn't find a booking with that confirmation number."
    verification = VerificationSessionService(db, rate_limiter=_verification_lockout())
    raw_token = args.get("verification_token") or verification.start(
        booking_id=str(booking.id), purpose="vapi_tool_access", call_id=call_id
    )
    record = verification.submit(
        raw_token=raw_token, booking=booking, email_or_phone=args.get("email_or_phone"), last_name=args.get("last_name")
    )
    if record.status == "VERIFIED":
        return f"Verified. verification_token: {raw_token} — use this for anything else on booking {booking.pnr}."
    if record.status == "FAILED":
        return "That didn't match our records, and this verification can't be retried — I'll need to transfer you to a human agent."
    return f"That didn't match. You can try again — verification_token: {raw_token}."


def _dispatch_get_booking(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    # Authorization already happened (in the webhook handler, before this
    # is called) against the SAME booking this loads — see that a second
    # time here only because we need the row's data, not to re-check
    # access to it.
    booking = BookingRepository(db).get_by_pnr(args["pnr"])
    if booking is None:
        return "I couldn't find a booking with that confirmation number."
    return _booking_summary(booking)


def _dispatch_create_booking(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    request = BookingCreateRequest(
        quote_id=args["quote_id"],
        passengers=[PassengerCreate(**p) for p in args["passengers"]],
        contact=ContactInfo(**args["contact"]),
        idempotency_key=args["idempotency_key"],
    )
    # T-5 (Phase 8): notifier constructed and passed ONLY here + in
    # _dispatch_create_payment_session below — see BookingService.
    # __init__'s comment for why _dispatch_modify_booking just below
    # stays unchanged (notifier=None, its default).
    notifier = NotificationService(db, get_email_provider(), get_sms_provider())
    service = BookingService(db, get_airline_provider(), get_idempotency_store(), notifier)
    booking = service.create_booking(request, actor=f"vapi_call:{call_id}", call_id=call_id)
    return f"Booked. Confirmation number {booking.pnr}. " + _booking_summary(booking)


def _dispatch_modify_booking(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    request = BookingModifyRequest(**args)
    service = BookingService(db, get_airline_provider(), get_idempotency_store())
    booking = service.modify_booking(request, actor=f"vapi_call:{call_id}", call_id=call_id)
    return f"Updated booking {booking.pnr}. " + _booking_summary(booking)


def _dispatch_cancel_booking(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    request = BookingCancelRequest(**args)
    service = CancellationService(db, get_airline_provider(), get_idempotency_store(), get_payment_provider())
    booking, already_cancelled = service.cancel(request, actor=f"vapi_call:{call_id}", call_id=call_id)
    if already_cancelled:
        return f"Booking {booking.pnr} was already cancelled."
    return f"Booking {booking.pnr} has been cancelled."


def _dispatch_add_passenger(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    pnr = args.pop("pnr")
    args.pop("verification_token", None)
    # Captured before constructing PassengerCreate below — PassengerService.
    # add_passenger() returns the updated Booking, not the passenger just
    # added, so these come from what we already know we're adding rather
    # than from the return value (confirmed by reading the service's
    # source while building this phase, not assumed).
    first_name, last_name = args["first_name"], args["last_name"]
    service = PassengerService(db, get_airline_provider())
    service.add_passenger(pnr, PassengerCreate(**args), actor=f"vapi_call:{call_id}", call_id=call_id)
    return f"Added {first_name} {last_name} to booking {pnr}."


def _dispatch_remove_passenger(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    service = PassengerService(db, get_airline_provider())
    service.remove_passenger(args["pnr"], args["booking_passenger_id"], actor=f"vapi_call:{call_id}", call_id=call_id)
    return f"Removed that passenger from booking {args['pnr']}."


def _dispatch_create_payment_session(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    request = PaymentSessionCreateRequest(**args)
    # T-5 (Phase 8): notifier constructed and passed here — closes the
    # gap docs/PAYMENTS.md §8 documented. also_sms is decided inside
    # PaymentService.create_payment_session itself (call_id is not None
    # for every Vapi-originated call, since it's always supplied here).
    notifier = NotificationService(db, get_email_provider(), get_sms_provider())
    service = PaymentService(db, get_payment_provider(), get_idempotency_store(), notifier)
    payment = service.create_payment_session(request, actor=f"vapi_call:{call_id}", call_id=call_id)
    # The URL is still returned as DATA for the assistant to work with —
    # this string is what the LLM sees, not literally what gets read
    # aloud to the caller (same as _booking_summary() above). Unlike
    # before T-5, the assistant CAN now tell the caller delivery is
    # happening: PaymentService.create_payment_session emails the link
    # (and additionally texts it, since this is a voice call) as a
    # system-triggered side effect — see NotificationService's docstring
    # for why this is best-effort and may occasionally fail silently
    # server-side rather than something the assistant should promise as
    # certain. See tool_schemas.py's create_payment_session description
    # and docs/PAYMENTS.md §8 (now updated) for the full reasoning.
    return (
        f"Payment link created for booking {payment.booking.pnr}, total {payment.amount} {payment.currency}. "
        f"It's being emailed and texted to the contact on file now — let the caller know to check their "
        f"phone/inbox in a moment. Link (for your reference, not to read aloud): {payment.checkout_url}"
    )


def _dispatch_get_payment_status(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    service = PaymentService(db, get_payment_provider(), get_idempotency_store())
    booking, payment = service.get_payment_status(args["pnr"])
    if payment is None:
        return f"Booking {booking.pnr} has no payment on file yet. Payment status: {booking.payment_status.lower()}."
    return (
        f"Booking {booking.pnr} payment status: {booking.payment_status.lower()} "
        f"(latest payment attempt: {payment.status.lower()}, {payment.amount} {payment.currency})."
    )


def _dispatch_transfer_to_human(args: dict, *, db: Session, actor: CurrentActor, call_id: str) -> str:
    # IMPLEMENTED — EXTERNAL VAPI VERIFICATION REQUIRED. This function
    # does NOT move the call — nothing in this webhook-triggered custom
    # tool can; only Vapi's own native `transferCall` tool (a phone
    # number/SIP/assistant destination configured on the Vapi Assistant
    # itself, static or resolved via a separate `transfer-destination-
    # request` webhook message this route doesn't currently handle) can
    # actually do that (confirmed against docs.vapi.ai/tools/transfer-
    # call and docs.vapi.ai/calls/call-dynamic-transfers while building
    # this phase). This tool's actual job is to log the escalation
    # (automatically, via the same ToolExecution row every tool call
    # gets — see _handle_one_tool_call) and tell the ASSISTANT to invoke
    # the real transfer next — see docs/VAPI.md for the required Vapi
    # dashboard configuration and system-prompt wiring.
    #
    # The wording below is deliberately an instruction back to the
    # assistant, not a claim to the caller — returning "Transferring you
    # now" here would be exactly the misleading-confirmation failure
    # mode this needs to avoid: the caller would hear that from the LLM
    # relaying it, believe a transfer is underway, and nothing would
    # actually be happening unless the assistant separately calls
    # transferCall.
    return "Escalation logged. Use the transfer tool now to connect them to a team member."


_DISPATCH: dict[str, Any] = {
    "search_flights": _dispatch_search_flights,
    "get_flight_details": _dispatch_get_flight_details,
    "get_aircraft_availability": _dispatch_get_aircraft_availability,
    "get_fare_quote": _dispatch_get_fare_quote,
    "get_cancellation_policy": _dispatch_get_cancellation_policy,
    "get_baggage_policy": _dispatch_get_baggage_policy,
    "verify_booking_customer": _dispatch_verify_booking_customer,
    "get_booking": _dispatch_get_booking,
    "create_booking": _dispatch_create_booking,
    "modify_booking": _dispatch_modify_booking,
    "cancel_booking": _dispatch_cancel_booking,
    "add_passenger": _dispatch_add_passenger,
    "remove_passenger": _dispatch_remove_passenger,
    "transfer_to_human": _dispatch_transfer_to_human,
    "create_payment_session": _dispatch_create_payment_session,
    "get_payment_status": _dispatch_get_payment_status,
}

# Tools whose mapped args carry a `pnr` that must be resolved to a real
# booking row (server-side truth) before authorization can be checked.
# verify_booking_customer is included even though it's PUBLIC — it still
# needs the booking row to check factors against.
_PNR_TOOLS = {
    "verify_booking_customer", "get_booking", "modify_booking", "cancel_booking",
    "add_passenger", "remove_passenger", "create_payment_session", "get_payment_status",
}


# --------------------------------------------------------------------- webhook endpoint


@router.post("/webhook")
def vapi_webhook(request: Request, body: dict = Body(default_factory=dict), db: Session = Depends(get_db)):
    settings = get_settings()
    auth = verify_webhook_request(dict(request.headers), configured_secret=settings.vapi_webhook_secret)
    if not auth.authenticated:
        # Not a tool-specific failure — this isn't Vapi at all (or the
        # server is misconfigured). §13's outer trust boundary; this is
        # the one case in this route that is allowed to be non-200 — see
        # module docstring.
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    # Webhook-level rate limit — a coarse abuse guard on the endpoint as
    # a whole (misconfigured/compromised integration, or noise from
    # senders that don't even hold the webhook secret), checked BEFORE
    # any parsing. Keyed by source IP, not by anything from the body —
    # see app.core.vapi.rate_limiting.webhook_rate_limit_key's docstring
    # for why. This is a second, non-200 rejection point alongside the
    # secret check above, for the same reason: "you're sending too much
    # traffic" is a transport-level fact about this HTTP request, not a
    # per-tool-call result, so it doesn't belong in the results[] array
    # Vapi expects for tool-calls specifically.
    source_ip = request.client.host if request.client else None
    webhook_limit = _webhook_rate_limiter().check(webhook_rate_limit_key(source_ip))
    if not webhook_limit.allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited"},
            headers={"Retry-After": str(int(webhook_limit.retry_after_seconds) + 1)},
        )

    message = body.get("message") if isinstance(body.get("message"), dict) else {}
    message_type = message.get("type")

    raw_call = message.get("call") if isinstance(message.get("call"), dict) else {}
    vapi_call_id = raw_call.get("id")
    assistant_id = (message.get("assistant") or {}).get("id") or raw_call.get("assistantId")

    if message_type == "end-of-call-report" and vapi_call_id:
        call = _get_or_create_call(db, vapi_call_id=vapi_call_id, assistant_id=assistant_id, raw_call=raw_call)
        call.status = "ended"
        call.ended_reason = message.get("endedReason")
        db.flush()
        db.commit()
        return JSONResponse(status_code=200, content={})

    if message_type != "tool-calls":
        # Vapi sends many other event types (status-update, speech-
        # update, transcript, ...) to the same Server URL. A response
        # body isn't expected for most of them (see module docstring) —
        # 200 + empty object acknowledges receipt without pretending to
        # have processed something this route doesn't handle.
        return JSONResponse(status_code=200, content={})

    if not vapi_call_id:
        return JSONResponse(status_code=200, content={"results": []})

    call = _get_or_create_call(db, vapi_call_id=vapi_call_id, assistant_id=assistant_id, raw_call=raw_call)
    db.commit()

    tool_calls = message.get("toolCallList")
    if not isinstance(tool_calls, list):
        tool_calls = message.get("toolCalls") if isinstance(message.get("toolCalls"), list) else []

    results = []
    for tool_call in tool_calls:
        results.append(
            _handle_one_tool_call(tool_call, db=db, call_id=vapi_call_id, call_pk=call.id, assistant_id=assistant_id)
        )
    db.commit()

    return JSONResponse(status_code=200, content={"results": results})


def _handle_one_tool_call(
    tool_call: dict, *, db: Session, call_id: str, call_pk, assistant_id: Optional[str]
) -> dict:
    vapi_tool_call_id = tool_call.get("id") or f"missing_{uuid.uuid4()}"
    function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
    tool_name = function.get("name", "")

    # Transport-level dedup: if Vapi retried delivery of the exact same
    # toolCallId (its webhook timed out waiting for our first response,
    # say) and we already recorded a completed outcome, don't re-run a
    # mutation.
    existing = ToolExecutionRepository(db).get_by_vapi_tool_call_id(vapi_tool_call_id)
    if existing is not None and existing.outcome is not None:
        # We don't retain the original result text (only a redacted args
        # snapshot + outcome/error_code), so a retry gets a short, honest
        # status rather than a fabricated repeat of the original wording.
        if existing.outcome == "success":
            return _ok(vapi_tool_call_id, "Already done.")
        return _err(vapi_tool_call_id, "That didn't go through — could you try again?")

    started = time.monotonic()
    if existing is not None:
        # existing.outcome is None here: a prior attempt for this exact
        # vapi_tool_call_id was logged but never reached _save_log() —
        # a genuine server crash mid-request (every NORMAL failure path
        # below does reach _save_log(), so this only happens on a real
        # crash, not an ordinary error). REUSE that row (an UPDATE) rather
        # than constructing a new ToolExecution with the same
        # vapi_tool_call_id, which would violate its unique constraint —
        # `existing` is already attached to this Session from the query
        # above, so mutating its fields and letting the same
        # ToolExecutionRepository.add()/flush() at the end of this
        # function run generates an UPDATE, not a second INSERT.
        #
        # This closes the SEQUENTIAL crash-then-retry case cleanly. It
        # does NOT close a genuinely CONCURRENT double-delivery (two
        # requests for the same vapi_tool_call_id, both reaching this
        # get_by_vapi_tool_call_id() call before either has committed a
        # row) — that's a classic check-then-act race that would need a
        # database-level `INSERT ... ON CONFLICT` or a serializable
        # transaction to close completely, neither of which can be
        # verified against a real database in this sandbox. Documented,
        # not silently assumed fixed. Note the severity this narrows to:
        # even in that race, the actual booking MUTATION underneath
        # (BookingService/CancellationService) is independently protected
        # by derive_idempotency_key() + IdempotencyStore — this table is
        # audit/observability bookkeeping, not the mutation-safety
        # mechanism, so the worst case here is a confusing ToolExecution
        # log, not a duplicate cancellation or double-booking.
        log = existing
        log.tool_name = tool_name
    else:
        log = ToolExecution(
            call_id=call_pk,
            vapi_tool_call_id=vapi_tool_call_id,
            tool_name=tool_name,
            arguments_redacted={},
            authorization_result="denied",
        )
        # Claim the row (and its unique constraint) immediately, before
        # any parsing/authorization/dispatch below — narrows, though
        # doesn't eliminate (see above), the window for the concurrent
        # case, since a second near-simultaneous request now has a real
        # chance of finding `existing` above instead of racing an INSERT.
        ToolExecutionRepository(db).add(log)

    # Per-call tool-execution rate limit — a DIFFERENT concern from the
    # webhook-level one in vapi_webhook(): that one guards the endpoint
    # as a whole; this one guards against one call_id (one phone call)
    # invoking tools excessively, e.g. a runaway/looping LLM. Checked
    # here, inside the per-tool-call handler, rather than once per
    # webhook POST, because Vapi can batch several tool calls into one
    # request (message.toolCallList) — the limit is on tool-call volume,
    # not on webhook-request volume, which the earlier check already
    # covers separately. A rate-limited call still gets a results[]
    # entry (never a non-200) — this is a tool-specific outcome from the
    # caller's point of view, unlike the auth/webhook-volume checks
    # above, which reject the whole request before we know it's even a
    # real tool-calls message.
    tool_limit = _tool_rate_limiter().check(tool_rate_limit_key(call_id))
    if not tool_limit.allowed:
        log.authorization_result = "denied"
        log.denial_reason = "rate_limited"
        _save_log(db, log, started)
        return _err(vapi_tool_call_id, "You're making requests a bit too quickly — let's slow down for a moment.")

    try:
        raw_args = parse_tool_call_arguments(function.get("arguments"))
        log.arguments_redacted = redact_value(raw_args)

        schema = VAPI_TOOL_SCHEMAS.get(tool_name)
        actor = _base_vapi_actor(call_id=call_id, assistant_id=assistant_id, tool_execution_id=vapi_tool_call_id)

        booking = None
        booking_id = None
        booking_customer_id = None
        pnr_for_mapping = raw_args.get("pnr")
        if tool_name in _PNR_TOOLS and pnr_for_mapping:
            booking = BookingRepository(db).get_by_pnr(str(pnr_for_mapping).strip().upper())
            if booking is None:
                log.authorization_result = "denied"
                log.denial_reason = "booking_not_found"
                _save_log(db, log, started)
                return _err(vapi_tool_call_id, "I couldn't find a booking with that confirmation number.")
            booking_id = str(booking.id)
            booking_customer_id = str(booking.customer_id) if booking.customer_id else None
            actor = _redeem_verification_token(
                actor, booking=booking, verification_token=raw_args.get("verification_token"), db=db
            )

        decision = authorize_vapi_tool_call(
            actor, tool_name=tool_name, booking_id=booking_id, booking_customer_id=booking_customer_id
        )
        if not decision.allowed:
            log.authorization_result = "denied"
            log.denial_reason = decision.reason
            _save_log(db, log, started)
            message_out = _AUTH_DENIAL_MESSAGES.get(decision.error_code or "", _DEFAULT_DENIAL_MESSAGE)
            return _err(vapi_tool_call_id, message_out)

        log.authorization_result = "allowed"

        if schema is None:
            log.outcome = "error"
            log.error_code = "UNKNOWN_TOOL"
            _save_log(db, log, started)
            return _err(vapi_tool_call_id, "I don't have a way to do that.")

        if not schema.implemented:
            log.outcome = "not_implemented"
            _save_log(db, log, started)
            return _ok(vapi_tool_call_id, NOT_YET_AVAILABLE_MESSAGE)

        mapper = TOOL_ARGUMENT_MAPPERS[tool_name]
        mapped = mapper(raw_args, call_id=call_id) if tool_name in MAPPERS_REQUIRING_CALL_ID else mapper(raw_args)
        if "idempotency_key" in mapped:
            log.idempotency_key = mapped["idempotency_key"]

        dispatch = _DISPATCH[tool_name]
        result_text = dispatch(mapped, db=db, actor=actor, call_id=call_id)

        log.outcome = "success"
        _save_log(db, log, started)
        return _ok(vapi_tool_call_id, result_text)

    except ArgumentMappingError as exc:
        log.outcome = "error"
        log.error_code = exc.code
        _save_log(db, log, started)
        return _err(vapi_tool_call_id, exc.message)
    except (ProviderError, PaymentProviderError, AppError) as exc:
        # ProviderError already covers FlightNotFoundError/
        # BookingNotFoundError/ProviderUnavailableError (its subclasses).
        # PaymentProviderError (Phase 6 Milestone 1) is a distinct type
        # from ProviderError — see app/providers/payments/base.py's
        # docstring — but gets identical handling here: its .message is
        # already user-safe (never a raw Stripe exception), same trust
        # level as everything else in this except clause.
        log.outcome = "error"
        log.error_code = getattr(exc, "code", type(exc).__name__)
        _save_log(db, log, started)
        # AppError/ProviderError messages are already written to be
        # user-safe (never a stack trace or internal detail) — see
        # app/core/exceptions.py — so it's fine to speak exc.args[0]/
        # exc.message directly, same trust level as the HTTP error
        # envelope the web routes already return for the same exceptions.
        return _err(vapi_tool_call_id, getattr(exc, "message", str(exc)) or "Something went wrong with that request.")
    except Exception:  # noqa: BLE001 — never let an unexpected error leak detail to the voice channel
        log.outcome = "error"
        log.error_code = "INTERNAL_ERROR"
        _save_log(db, log, started)
        return _err(vapi_tool_call_id, "Something went wrong on my end — let me transfer you to a human agent.")


def _save_log(db: Session, log: ToolExecution, started_at: float) -> None:
    log.latency_ms = int((time.monotonic() - started_at) * 1000)
    ToolExecutionRepository(db).add(log)
