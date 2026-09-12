"""
T-7 (docs/TASK_BOARD.md, WBS-6.2, Phase 10) — the voice conversation test
suite `tests/voice/README.md` reserved a spot for. Run with:

    cd apps/api && python3 -m unittest tests.test_voice_conversation_core -v

WORK_BREAKDOWN_STRUCTURE.md's WBS-6.2 describes this as covering "the 7
example test cases in the spec" but then names only six: missing-info
collection, verify-before-cancel, no booking without a quote, quote-only
on price question, human transfer on request, never reveal passport
number. That count mismatch is reproduced here honestly rather than
resolved by inventing a plausible-sounding seventh case — the original
Master Build Prompt text isn't committed anywhere in this repository (see
docs/PROJECT_ROADMAP.md's "Required reading" note on why), so there is no
canonical source in-repo to check the missing case against. Six scenarios
below, one test class each, named after the WBS's own wording.

WHAT THIS SUITE DOES AND DOES NOT PROVE
Every one of these six scenarios, as the spec states them, is about the
Vapi ASSISTANT's live conversational behavior — a real LLM, under a real
system prompt, talking to a real caller. This suite cannot exercise any
of that: there is no live Vapi account in this or any sandbox this
project has run in (docs/WORK_BREAKDOWN_STRUCTURE.md WBS-2.2-2.5 remain
BLOCKED for exactly this reason), and even with one, "did the LLM behave"
isn't a dependency-free, deterministic thing to assert.

What IS dependency-free and deterministic is the backend guarantee MASTER
_RULES.md's own framing rests on — "the backend is always the source of
truth, never the LLM's own claims" — that makes each scenario hold
regardless of what the assistant does or doesn't say. If the LLM tries to
book without a quote, hallucinates that a cancellation was verified, or
narrates a transfer that didn't happen, the backend must independently
refuse or correct that outcome. That is what every test below actually
exercises: the real argument-mapping/authorization/provider code the
Vapi webhook dispatch table (app/api/routes/vapi.py) calls into, not a
simulation of one. Nothing here is fabricated to fit the scenario name —
every assertion below traces to an actual function in app/core/vapi/,
app/core/security/, app/providers/airline/, or app/core/encryption.py.

This is therefore an acceptance/traceability layer over guarantees that
are, in several cases, already separately exercised elsewhere (e.g.
tests/test_vapi_core.py's MutatingToolMappingTests already covers cancel_
booking's verification-token requirement from the argument-mapping
layer's own perspective). Duplicating an assertion here is deliberate,
not sloppy: this file's organizing question is "does spec §56's scenario
N hold", not "does function N behave" — a different, additive kind of
coverage, the same way a docs/handoffs §11 security pass re-reads code
already covered by unit tests through a different lens.
"""

from __future__ import annotations

import re
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/api/ on sys.path

from app.core.encryption import mask_for_speech
from app.core.security.actor import ActorType, CurrentActor
from app.core.security.vapi_authorization import (
    TOOL_AUTHORIZATION_MATRIX,
    VAPI_ASSISTANT_PERMISSIONS,
    ToolSensitivity,
    authorize_vapi_tool_call,
)
from app.core.vapi.argument_mapping import (
    ArgumentMappingError,
    map_cancel_booking,
    map_create_booking,
    map_transfer_to_human,
)
from app.core.vapi.tool_schemas import VAPI_TOOL_SCHEMAS
from app.providers.airline.base import PassengerInput, ProviderError
from app.providers.airline.mock import MockAirlineProvider


FRA_NOW = datetime(2026, 8, 31, 9, 0, tzinfo=ZoneInfo("Europe/Berlin"))  # a Monday


def _vapi_actor(*, authenticated: bool = True, verified_booking_id: str | None = None,
                purpose: str | None = None, permissions=VAPI_ASSISTANT_PERMISSIONS) -> CurrentActor:
    """Mirrors tests/test_security_core.py's own `_vapi_actor` helper, but
    defaults to VAPI_ASSISTANT_PERMISSIONS — the actual fixed permission
    set app/api/routes/vapi.py's webhook handler grants a real Vapi
    actor — rather than a hand-picked test subset, so "authorized" here
    means "authorized for the real assistant", not "authorized for a
    permission set this test happened to invent"."""
    return CurrentActor(
        actor_type=ActorType.VAPI_AGENT, vapi_authenticated=authenticated, call_id="call_1",
        assistant_id="asst_1", permissions=permissions,
        verified_booking_id=verified_booking_id, verified_purpose=purpose,
        booking_verification_status="VERIFIED" if verified_booking_id else None,
    )


def _quoted_provider(adults: int = 1):
    """A MockAirlineProvider with one real, unexpired quote already
    issued — the starting point every scenario below either relies on or
    deliberately withholds."""
    provider = MockAirlineProvider(clock=lambda: FRA_NOW)
    offers = provider.search_flights(origin="FRA", destination="DXB", departure_date=date(2026, 9, 4), adults=adults)
    quote = provider.get_fare_quote(offers[0].flight_id, adults=adults)
    return provider, quote


# ---------------------------------------------------------------------------
# Scenario 1: "missing-info collection" — customer says 'book it' with no
# quoted flight (or any other required detail) -> agent must not book, and
# must be told exactly what's still needed so it can ask.
# ---------------------------------------------------------------------------
class MissingInfoCollectionTests(unittest.TestCase):
    _BASE_ARGS = {
        "quote_id": "quote_abc123",
        "passengers": [{"first_name": "Anna", "last_name": "Keller"}],
        "contact_email": "anna@example.com",
        "contact_phone": "+4915112345",
    }

    def test_missing_quote_id_is_refused_not_booked(self):
        args = dict(self._BASE_ARGS)
        del args["quote_id"]
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_create_booking(args, call_id="call_1")
        self.assertEqual(ctx.exception.code, "MISSING_ARGUMENT")

    def test_missing_passengers_is_refused(self):
        args = dict(self._BASE_ARGS)
        del args["passengers"]
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_create_booking(args, call_id="call_1")
        self.assertEqual(ctx.exception.code, "MISSING_ARGUMENT")

    def test_empty_passenger_list_is_refused(self):
        args = dict(self._BASE_ARGS, passengers=[])
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_create_booking(args, call_id="call_1")
        self.assertEqual(ctx.exception.code, "MISSING_ARGUMENT")

    def test_passenger_missing_last_name_is_refused(self):
        args = dict(self._BASE_ARGS, passengers=[{"first_name": "Anna"}])
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_create_booking(args, call_id="call_1")
        self.assertEqual(ctx.exception.code, "MISSING_ARGUMENT")

    def test_missing_contact_email_is_refused(self):
        args = dict(self._BASE_ARGS)
        del args["contact_email"]
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_create_booking(args, call_id="call_1")
        self.assertEqual(ctx.exception.code, "MISSING_ARGUMENT")

    def test_refusal_message_is_speakable_not_an_internal_error(self):
        # The agent relays this string back to the caller verbatim (see
        # app/api/routes/vapi.py's ArgumentMappingError handling) — it must
        # read like something you'd say out loud, never a Python repr, a
        # field name in snake_case with no article, or a stack trace.
        args = dict(self._BASE_ARGS)
        del args["contact_phone"]
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_create_booking(args, call_id="call_1")
        message = ctx.exception.message
        self.assertNotIn("Traceback", message)
        self.assertNotIn("dict", message)
        self.assertIn("contact_phone", message)  # names exactly what's missing


# ---------------------------------------------------------------------------
# Scenario 2: "no booking without a quote" — there is no code path from a
# bare flight/price mention to a confirmed booking; a quote_id from a real,
# unexpired get_fare_quote call is the only door in.
# ---------------------------------------------------------------------------
class NoBookingWithoutAQuoteTests(unittest.TestCase):
    def test_a_made_up_quote_id_cannot_produce_a_booking(self):
        provider, _real_quote = _quoted_provider()
        with self.assertRaises(ProviderError) as ctx:
            provider.create_booking(
                quote_id="quote_this_was_never_issued", passengers=[PassengerInput(first_name="A", last_name="B")],
                contact_email="a@example.com", contact_phone="+491", idempotency_key="k1",
            )
        self.assertEqual(ctx.exception.code, "FARE_EXPIRED")

    def test_an_expired_quote_cannot_produce_a_booking(self):
        provider, quote = _quoted_provider()
        provider._now = lambda: FRA_NOW + timedelta(minutes=16)  # past the 15-minute validity window
        with self.assertRaises(ProviderError) as ctx:
            provider.create_booking(
                quote_id=quote.quote_id, passengers=[PassengerInput(first_name="A", last_name="B")],
                contact_email="a@example.com", contact_phone="+491", idempotency_key="k1",
            )
        self.assertEqual(ctx.exception.code, "FARE_EXPIRED")

    def test_create_booking_schema_declares_quote_id_required(self):
        # The JSON schema sent to Vapi itself asks for a quote_id (the
        # first layer that might make an LLM ask before calling at all) —
        # backed up by map_create_booking's own independent Python-level
        # check (test_missing_quote_id_is_refused_not_booked above), which
        # holds even if the LLM ignores the schema's "required" list.
        schema = VAPI_TOOL_SCHEMAS["create_booking"]
        self.assertIn("quote_id", schema.parameters["required"])

    def test_no_tool_other_than_create_booking_can_confirm_a_reservation(self):
        # Every OTHER tool that touches a flight/fare is either read-only
        # or operates on a booking that must already exist — i.e. nothing
        # in the tool surface offers a second door into a confirmed
        # booking that bypasses create_booking's quote_id requirement.
        reservation_creating_tools = {
            name for name, schema in VAPI_TOOL_SCHEMAS.items()
            if schema.mutates and schema.implemented and TOOL_AUTHORIZATION_MATRIX.get(name, {}).get(
                "sensitivity"
            ) != ToolSensitivity.REQUIRES_VERIFIED_BOOKING
        }
        # PUBLIC + mutates=True + implemented tools are the only ones that
        # could conceivably create a booking out of nothing (everything
        # REQUIRES_VERIFIED_BOOKING already presupposes a prior booking).
        self.assertEqual(reservation_creating_tools, {"create_booking"})


# ---------------------------------------------------------------------------
# Scenario 3: "quote-only on price question" — asking what something costs
# can never itself result in a purchase.
# ---------------------------------------------------------------------------
class QuoteOnlyOnPriceQuestionTests(unittest.TestCase):
    def test_search_flights_is_read_only(self):
        schema = VAPI_TOOL_SCHEMAS["search_flights"]
        self.assertFalse(schema.mutates)
        self.assertFalse(schema.requires_confirmation)

    def test_get_fare_quote_is_read_only(self):
        schema = VAPI_TOOL_SCHEMAS["get_fare_quote"]
        self.assertFalse(schema.mutates)
        self.assertFalse(schema.requires_confirmation)

    def test_issuing_a_quote_does_not_touch_provider_booking_state(self):
        provider, _quote = _quoted_provider()
        self.assertEqual(len(provider._bookings), 0)  # a quote alone books nothing

    def test_create_booking_is_the_only_mutating_step_and_it_requires_confirmation(self):
        # Reinforces scenario 2's guarantee from the opposite direction:
        # the one tool capable of turning a price question into a
        # purchase also independently requires the caller's explicit yes
        # (MASTER_RULES.md §3), on top of needing a real quote_id.
        schema = VAPI_TOOL_SCHEMAS["create_booking"]
        self.assertTrue(schema.mutates)
        self.assertTrue(schema.requires_confirmation)


# ---------------------------------------------------------------------------
# Scenario 4: "verify-before-cancel" — a caller cannot cancel a booking
# without first passing identity verification for THAT booking.
# ---------------------------------------------------------------------------
class VerifyBeforeCancelTests(unittest.TestCase):
    def test_cancel_mapper_requires_a_verification_token(self):
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_cancel_booking({"pnr": "ABC123", "customer_confirmed": True}, call_id="call_1")
        self.assertEqual(ctx.exception.code, "MISSING_ARGUMENT")

    def test_cancel_mapper_requires_explicit_confirmation_even_when_verified(self):
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_cancel_booking({"pnr": "ABC123", "verification_token": "tok_1"}, call_id="call_1")
        self.assertEqual(ctx.exception.code, "CONFIRMATION_REQUIRED")

    def test_authorization_matrix_gates_cancel_on_a_verified_booking(self):
        entry = TOOL_AUTHORIZATION_MATRIX["cancel_booking"]
        self.assertEqual(entry["sensitivity"], ToolSensitivity.REQUIRES_VERIFIED_BOOKING)

    def test_unverified_vapi_actor_is_denied_cancel_even_with_full_permissions(self):
        # Defense in depth beyond the mapper: even if the argument-mapping
        # check above were somehow bypassed, the authorization layer
        # independently refuses an unverified caller — full
        # VAPI_ASSISTANT_PERMISSIONS included, since permission and
        # verification are deliberately two separate gates.
        actor = _vapi_actor(verified_booking_id=None)
        decision = authorize_vapi_tool_call(actor, tool_name="cancel_booking", booking_id="bk_1", booking_customer_id="cust_A")
        self.assertFalse(decision.allowed)

    def test_verified_for_a_different_booking_is_still_denied(self):
        # "vapi_tool_access" is the literal purpose authorize_vapi_tool_call
        # itself passes to authorize_booking_access — see that function.
        actor = _vapi_actor(verified_booking_id="bk_OTHER", purpose="vapi_tool_access")
        decision = authorize_vapi_tool_call(actor, tool_name="cancel_booking", booking_id="bk_1", booking_customer_id="cust_A")
        self.assertFalse(decision.allowed)

    def test_verified_for_the_right_booking_is_allowed(self):
        actor = _vapi_actor(verified_booking_id="bk_1", purpose="vapi_tool_access")
        decision = authorize_vapi_tool_call(actor, tool_name="cancel_booking", booking_id="bk_1", booking_customer_id="cust_A")
        self.assertTrue(decision.allowed)


# ---------------------------------------------------------------------------
# Scenario 5: "human transfer on request" — a caller who asks for a human
# must always be able to reach one; nothing about this tool may block on
# permissions, verification, or confirmation the way a booking action does.
# ---------------------------------------------------------------------------
class HumanTransferOnRequestTests(unittest.TestCase):
    def test_transfer_is_public_no_verification_required(self):
        entry = TOOL_AUTHORIZATION_MATRIX["transfer_to_human"]
        self.assertEqual(entry["sensitivity"], ToolSensitivity.PUBLIC)

    def test_transfer_needs_no_confirmation_or_mutation_flag(self):
        schema = VAPI_TOOL_SCHEMAS["transfer_to_human"]
        self.assertFalse(schema.requires_confirmation)

    def test_real_assistant_permission_set_can_always_invoke_transfer(self):
        actor = _vapi_actor()  # no verified booking at all — a transfer must not need one
        decision = authorize_vapi_tool_call(actor, tool_name="transfer_to_human")
        self.assertTrue(decision.allowed)

    def test_mapper_never_blocks_on_a_missing_reason(self):
        # A caller who just says "get me a person" with no elaboration
        # must still be transferable — "reason" degrades gracefully
        # instead of being required.
        result = map_transfer_to_human({})
        self.assertEqual(result["reason"], "not specified")

    def test_dispatch_wording_never_claims_a_completed_live_transfer(self):
        # app/api/routes/vapi.py needs FastAPI/SQLAlchemy to import, so
        # this can't call _dispatch_transfer_to_human directly in this
        # sandbox — instead this reads the function's own source text and
        # checks its literal response strings, which is what's actually
        # spoken back to the caller, never claim a transfer that the
        # backend itself didn't perform (it only logs an escalation and
        # tells the agent to invoke Vapi's own transferCall mechanism —
        # see that function's docstring). A live-stack run of
        # tests/test_vapi_api.py is the equivalent executable check once
        # FastAPI is installed; this is the dependency-free stand-in.
        vapi_route_path = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "vapi.py"
        source = vapi_route_path.read_text()
        match = re.search(
            r"^def _dispatch_transfer_to_human\(.*?\n(?=^def )", source, re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(match, "could not locate _dispatch_transfer_to_human in app/api/routes/vapi.py")
        body = match.group(0).lower()
        forbidden_phrases = [
            "transferring you now", "you are now connected", "you're now connected",
            "i've connected you", "i have connected you", "connecting you now",
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(phrase, body, f"dispatch wording must never claim a transfer already happened: {phrase!r}")


# ---------------------------------------------------------------------------
# Scenario 6: "never reveal passport number" — anything a tool response
# might cause the agent to read back aloud must never include a full
# passport number.
# ---------------------------------------------------------------------------
class PassportNeverReadAloudTests(unittest.TestCase):
    def test_mask_for_speech_hides_all_but_last_four(self):
        self.assertEqual(mask_for_speech("X1234567"), "****4567")

    def test_mask_for_speech_never_lengthens_or_reveals_more_on_long_numbers(self):
        masked = mask_for_speech("PA9988776655")
        self.assertTrue(masked.endswith("6655"))
        self.assertEqual(len(masked), len("PA9988776655"))
        self.assertNotIn("9988", masked)

    def test_mask_for_speech_handles_short_values_without_leaking_them(self):
        # <=4 chars: even the "last 4" carve-out would reveal the whole
        # thing, so the function falls back to a fixed, fully-opaque mask.
        for short_value in ("AB12", "Z9", "", "X"):
            self.assertEqual(mask_for_speech(short_value), "***")

    def test_mask_for_speech_is_importable_without_pydantic_or_structlog(self):
        # Regression test for the T-7 finding fixed in
        # app/core/encryption.py: this module used to import app.core.
        # config/app.core.logging at MODULE level, so merely importing it
        # required pydantic + structlog — neither installed in this
        # sandbox — meaning this exact safety-critical function could
        # never run in the dependency-free tier before this fix. The fact
        # that this test file's own module-level `from app.core.encryption
        # import mask_for_speech` succeeded at all (see the top of this
        # file) is most of the proof; this test just makes that fact
        # explicit and named, so a future regression fails loudly here
        # rather than silently via an ImportError at collection time.
        import sys as _sys
        self.assertNotIn("pydantic", _sys.modules, "importing this module should not require pydantic")
        self.assertNotIn("structlog", _sys.modules, "importing this module should not require structlog")


if __name__ == "__main__":
    unittest.main()
