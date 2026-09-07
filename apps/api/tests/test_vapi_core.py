"""
Phase 5 dependency-free tests for app/core/security/vapi_webhook_auth.py
and app/core/vapi/*.py.

Runs the same way as tests/test_core_logic.py and tests/test_security_core.py:

    python3 -m unittest tests.test_vapi_core -v

No FastAPI/SQLAlchemy/Pydantic import anywhere in this file — that's the
point (see app/core/vapi/__init__.py's docstring).
"""

from __future__ import annotations

import unittest

from app.core.security.vapi_authorization import TOOL_AUTHORIZATION_MATRIX, ToolSensitivity
from app.core.security.rate_limiter import BackoffLockout, InMemoryRateLimitStore, build_rate_limiter
from app.core.security.vapi_webhook_auth import verify_webhook_request
from app.core.vapi.argument_mapping import (
    TOOL_ARGUMENT_MAPPERS,
    ArgumentMappingError,
    map_add_passenger,
    map_cancel_booking,
    map_create_booking,
    map_create_payment_session,
    map_get_aircraft_availability,
    map_get_booking,
    map_get_payment_status,
    map_modify_booking,
    map_remove_passenger,
    map_search_flights,
    map_verify_booking_customer,
    parse_tool_call_arguments,
)
from app.core.vapi.rate_limiting import tool_rate_limit_key, webhook_rate_limit_key
from app.core.vapi.tool_schemas import VAPI_TOOL_SCHEMAS, as_vapi_function_definitions


# ---------------------------------------------------------------------------
# Webhook shared-secret verification
# ---------------------------------------------------------------------------


class WebhookAuthTests(unittest.TestCase):
    def test_rejects_when_no_secret_configured(self):
        result = verify_webhook_request({"X-Vapi-Secret": "anything"}, configured_secret=None)
        self.assertFalse(result.authenticated)
        self.assertEqual(result.reason, "webhook_secret_not_configured")

    def test_rejects_when_no_header_presented(self):
        result = verify_webhook_request({}, configured_secret="top-secret")
        self.assertFalse(result.authenticated)
        self.assertEqual(result.reason, "no_secret_presented")

    def test_rejects_wrong_secret(self):
        result = verify_webhook_request({"X-Vapi-Secret": "wrong"}, configured_secret="top-secret")
        self.assertFalse(result.authenticated)
        self.assertEqual(result.reason, "secret_mismatch")

    def test_accepts_correct_x_vapi_secret_header(self):
        result = verify_webhook_request({"X-Vapi-Secret": "top-secret"}, configured_secret="top-secret")
        self.assertTrue(result.authenticated)

    def test_header_matching_is_case_insensitive(self):
        result = verify_webhook_request({"x-vapi-secret": "top-secret"}, configured_secret="top-secret")
        self.assertTrue(result.authenticated)

    def test_accepts_authorization_bearer_as_equivalent(self):
        result = verify_webhook_request({"Authorization": "Bearer top-secret"}, configured_secret="top-secret")
        self.assertTrue(result.authenticated)

    def test_bearer_prefix_is_required(self):
        result = verify_webhook_request({"Authorization": "top-secret"}, configured_secret="top-secret")
        self.assertFalse(result.authenticated)

    def test_x_vapi_secret_takes_priority_over_authorization(self):
        # If both are present and only one is correct, the request should
        # still be accepted if X-Vapi-Secret (checked first) is right,
        # regardless of what's in Authorization.
        result = verify_webhook_request(
            {"X-Vapi-Secret": "top-secret", "Authorization": "Bearer garbage"},
            configured_secret="top-secret",
        )
        self.assertTrue(result.authenticated)

    def test_empty_string_secret_is_not_presented(self):
        result = verify_webhook_request({"X-Vapi-Secret": ""}, configured_secret="top-secret")
        self.assertFalse(result.authenticated)
        self.assertEqual(result.reason, "no_secret_presented")


# ---------------------------------------------------------------------------
# Tool schema registry <-> authorization matrix consistency
# ---------------------------------------------------------------------------


class ToolRegistryConsistencyTests(unittest.TestCase):
    """The exact kind of check that would have caught this phase's own
    handoff-vs-code naming drift (§9's VAPI_TOOL_MATRIX vs. the real
    TOOL_AUTHORIZATION_MATRIX name; §11's update_booking vs. the real
    modify_booking) had it been code instead of prose."""

    def test_every_schema_tool_has_an_authorization_entry(self):
        missing = set(VAPI_TOOL_SCHEMAS) - set(TOOL_AUTHORIZATION_MATRIX)
        self.assertEqual(missing, set(), f"tools with a Vapi schema but no authorization entry: {missing}")

    def test_authorization_entries_without_a_schema_are_exactly_staff_only(self):
        # refund_payment / configure_assistant are intentionally never
        # exposed as an LLM-callable tool (STAFF_OR_ADMIN_ONLY — a voice
        # agent can never hold that sensitivity's requirements, so there
        # is nothing for it to call). Any OTHER matrix entry missing a
        # schema is a real gap, not an intentional exclusion.
        extra = set(TOOL_AUTHORIZATION_MATRIX) - set(VAPI_TOOL_SCHEMAS)
        non_staff_extra = {
            name for name in extra if TOOL_AUTHORIZATION_MATRIX[name]["sensitivity"] != ToolSensitivity.STAFF_OR_ADMIN_ONLY
        }
        self.assertEqual(non_staff_extra, set(), f"non-staff tools missing a Vapi schema: {non_staff_extra}")

    def test_every_implemented_schema_has_an_argument_mapper(self):
        for name, schema in VAPI_TOOL_SCHEMAS.items():
            if schema.implemented:
                self.assertIn(name, TOOL_ARGUMENT_MAPPERS, f"{name} is marked implemented but has no argument mapper")

    def test_unimplemented_tools_have_no_argument_mapper(self):
        # Guards the inverse mistake: a tool marked implemented=False that
        # actually has a mapper wired up would silently start working
        # without anyone updating tool_schemas.py's `implemented` flag —
        # this test forces both to move together.
        for name, schema in VAPI_TOOL_SCHEMAS.items():
            if not schema.implemented:
                self.assertNotIn(name, TOOL_ARGUMENT_MAPPERS, f"{name} is marked NOT implemented but has a mapper")

    def test_function_definitions_shape(self):
        defs = as_vapi_function_definitions()
        self.assertEqual(len(defs), len(VAPI_TOOL_SCHEMAS))
        names = {d["function"]["name"] for d in defs}
        self.assertEqual(names, set(VAPI_TOOL_SCHEMAS))
        for d in defs:
            self.assertEqual(d["type"], "function")
            params = d["function"]["parameters"]
            self.assertEqual(params["type"], "object")
            for required_field in params["required"]:
                self.assertIn(required_field, params["properties"], f"{d['function']['name']}: required field {required_field!r} not in properties")

    def test_verify_booking_customer_never_exposes_purpose_to_the_llm(self):
        # The Vapi channel always verifies for one fixed purpose — letting
        # the LLM see/set `purpose` would be a dangling, misleading
        # parameter (see tool_schemas.py's module docstring).
        params = VAPI_TOOL_SCHEMAS["verify_booking_customer"].parameters
        self.assertNotIn("purpose", params["properties"])


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class ParseToolCallArgumentsTests(unittest.TestCase):
    def test_accepts_dict_directly(self):
        self.assertEqual(parse_tool_call_arguments({"a": 1}), {"a": 1})

    def test_parses_json_string(self):
        self.assertEqual(parse_tool_call_arguments('{"a": 1}'), {"a": 1})

    def test_none_becomes_empty_dict(self):
        self.assertEqual(parse_tool_call_arguments(None), {})

    def test_empty_string_becomes_empty_dict(self):
        self.assertEqual(parse_tool_call_arguments("   "), {})

    def test_invalid_json_raises(self):
        with self.assertRaises(ArgumentMappingError):
            parse_tool_call_arguments("{not json")

    def test_json_array_raises(self):
        with self.assertRaises(ArgumentMappingError):
            parse_tool_call_arguments("[1, 2, 3]")

    def test_unsupported_type_raises(self):
        with self.assertRaises(ArgumentMappingError):
            parse_tool_call_arguments(12345)


# ---------------------------------------------------------------------------
# Argument mapping — read-only tools
# ---------------------------------------------------------------------------


class ReadOnlyMappingTests(unittest.TestCase):
    def test_search_flights_maps_and_defaults(self):
        mapped = map_search_flights(
            {"origin": "fra", "destination": "jfk", "departure_date": "2026-10-01", "adults": 2}
        )
        self.assertEqual(mapped["origin"], "FRA")
        self.assertEqual(mapped["destination"], "JFK")
        self.assertEqual(mapped["children"], 0)
        self.assertEqual(mapped["cabin_class"], "economy")
        self.assertFalse(mapped["direct_only"])

    def test_search_flights_missing_required_raises(self):
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_search_flights({"origin": "FRA"})
        self.assertEqual(ctx.exception.code, "MISSING_ARGUMENT")

    def test_aircraft_availability_all_optional(self):
        self.assertEqual(
            map_get_aircraft_availability({}),
            {"origin": None, "category": None, "on_date": None, "min_seats": None},
        )

    def test_pnr_is_normalized_to_uppercase(self):
        mapped = map_get_booking({"pnr": "abc123", "verification_token": "tok"})
        self.assertEqual(mapped["pnr"], "ABC123")

    def test_pnr_wrong_length_raises(self):
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_get_booking({"pnr": "ABC", "verification_token": "tok"})
        self.assertEqual(ctx.exception.code, "INVALID_ARGUMENTS")

    def test_verify_booking_customer_requires_email_or_last_name(self):
        with self.assertRaises(ArgumentMappingError):
            map_verify_booking_customer({"pnr": "ABC123"})

    def test_verify_booking_customer_accepts_last_name_alone(self):
        mapped = map_verify_booking_customer({"pnr": "ABC123", "last_name": "Müller"})
        self.assertEqual(mapped["last_name"], "Müller")
        self.assertIsNone(mapped["email_or_phone"])

    def test_verify_booking_customer_purpose_is_never_llm_controlled(self):
        # Even if a malicious/confused tool call smuggles in its own
        # "purpose", the mapped result must still be the one fixed value
        # authorize_vapi_tool_call() actually checks against.
        mapped = map_verify_booking_customer(
            {"pnr": "ABC123", "last_name": "Müller", "purpose": "cancel_booking"}
        )
        self.assertEqual(mapped["purpose"], "vapi_tool_access")


# ---------------------------------------------------------------------------
# Argument mapping — mutating tools: confirmation + idempotency
# ---------------------------------------------------------------------------


class MutatingToolMappingTests(unittest.TestCase):
    def test_cancel_booking_requires_verification_token(self):
        with self.assertRaises(ArgumentMappingError):
            map_cancel_booking({"pnr": "ABC123", "customer_confirmed": True}, call_id="call_1")

    def test_cancel_booking_rejects_missing_confirmation(self):
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_cancel_booking({"pnr": "ABC123", "verification_token": "tok"}, call_id="call_1")
        self.assertEqual(ctx.exception.code, "CONFIRMATION_REQUIRED")

    def test_cancel_booking_rejects_truthy_non_boolean_confirmation(self):
        # "true" the string, and 1 the int, are both truthy in Python but
        # must NOT satisfy a confirmation gate that's supposed to mean
        # "the LLM explicitly set this to boolean True after the customer
        # said yes." Only the literal bool True may pass.
        for bad_value in ("true", "yes", 1, "True"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaises(ArgumentMappingError) as ctx:
                    map_cancel_booking(
                        {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": bad_value},
                        call_id="call_1",
                    )
                self.assertEqual(ctx.exception.code, "CONFIRMATION_REQUIRED")

    def test_cancel_booking_accepts_boolean_true(self):
        mapped = map_cancel_booking(
            {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": True}, call_id="call_1"
        )
        self.assertTrue(mapped["customer_confirmed"] is True)
        self.assertTrue(mapped["idempotency_key"].startswith("idem_"))

    def test_cancel_booking_idempotency_key_is_deterministic_per_call(self):
        args = {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": True}
        first = map_cancel_booking(args, call_id="call_1")
        second = map_cancel_booking(args, call_id="call_1")
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])

    def test_cancel_booking_idempotency_key_differs_across_calls(self):
        args = {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": True}
        a = map_cancel_booking(args, call_id="call_1")
        b = map_cancel_booking(args, call_id="call_2")
        self.assertNotEqual(a["idempotency_key"], b["idempotency_key"])

    def test_cancel_booking_idempotency_key_differs_for_different_bookings(self):
        a = map_cancel_booking(
            {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": True}, call_id="call_1"
        )
        b = map_cancel_booking(
            {"pnr": "XYZ789", "verification_token": "tok", "customer_confirmed": True}, call_id="call_1"
        )
        self.assertNotEqual(a["idempotency_key"], b["idempotency_key"])

    def test_modify_booking_requires_at_least_one_change(self):
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_modify_booking(
                {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": True}, call_id="call_1"
            )
        self.assertEqual(ctx.exception.code, "MISSING_ARGUMENT")

    def test_modify_booking_accepts_a_single_change(self):
        mapped = map_modify_booking(
            {
                "pnr": "ABC123",
                "verification_token": "tok",
                "customer_confirmed": True,
                "new_contact_phone": "+491234567",
            },
            call_id="call_1",
        )
        self.assertEqual(mapped["new_contact_phone"], "+491234567")
        self.assertIsNone(mapped["new_flight_id"])

    def test_remove_passenger_rejects_missing_confirmation(self):
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_remove_passenger({"pnr": "ABC123", "verification_token": "tok", "booking_passenger_id": "p1"})
        self.assertEqual(ctx.exception.code, "CONFIRMATION_REQUIRED")

    # --- Phase 6 Milestone 1: payments ---

    def test_create_payment_session_requires_verification_token(self):
        with self.assertRaises(ArgumentMappingError):
            map_create_payment_session({"pnr": "ABC123", "customer_confirmed": True}, call_id="call_1")

    def test_create_payment_session_rejects_missing_confirmation(self):
        with self.assertRaises(ArgumentMappingError) as ctx:
            map_create_payment_session({"pnr": "ABC123", "verification_token": "tok"}, call_id="call_1")
        self.assertEqual(ctx.exception.code, "CONFIRMATION_REQUIRED")

    def test_create_payment_session_rejects_truthy_non_boolean_confirmation(self):
        # Same rule as cancel_booking/modify_booking/remove_passenger —
        # see test_cancel_booking_rejects_truthy_non_boolean_confirmation.
        for bad_value in ("true", "yes", 1, "True"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaises(ArgumentMappingError) as ctx:
                    map_create_payment_session(
                        {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": bad_value},
                        call_id="call_1",
                    )
                self.assertEqual(ctx.exception.code, "CONFIRMATION_REQUIRED")

    def test_create_payment_session_accepts_boolean_true(self):
        mapped = map_create_payment_session(
            {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": True}, call_id="call_1"
        )
        self.assertTrue(mapped["customer_confirmed"] is True)
        self.assertTrue(mapped["idempotency_key"].startswith("idem_"))
        # No amount/currency field exists anywhere in the mapped output —
        # see PaymentSessionCreateRequest's docstring: there is nothing
        # here for a forged/mistaken amount to flow through even if a
        # future prompt change somehow got the LLM to try to supply one.
        self.assertNotIn("amount", mapped)
        self.assertNotIn("currency", mapped)

    def test_create_payment_session_ignores_llm_supplied_amount(self):
        # Belt-and-braces: even if the tool call somehow included an
        # amount field (it isn't in the JSON schema's parameters at all,
        # so a spec-following LLM never would), the mapper only ever
        # reads pnr/verification_token/customer_confirmed — an extra key
        # is simply dropped, never forwarded.
        mapped = map_create_payment_session(
            {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": True, "amount": 999999},
            call_id="call_1",
        )
        self.assertNotIn("amount", mapped)

    def test_create_payment_session_idempotency_key_is_deterministic_per_call(self):
        args = {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": True}
        first = map_create_payment_session(args, call_id="call_1")
        second = map_create_payment_session(args, call_id="call_1")
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])

    def test_create_payment_session_idempotency_key_differs_across_calls(self):
        args = {"pnr": "ABC123", "verification_token": "tok", "customer_confirmed": True}
        a = map_create_payment_session(args, call_id="call_1")
        b = map_create_payment_session(args, call_id="call_2")
        self.assertNotEqual(a["idempotency_key"], b["idempotency_key"])

    def test_get_payment_status_requires_verification_token(self):
        with self.assertRaises(ArgumentMappingError):
            map_get_payment_status({"pnr": "ABC123"})

    def test_get_payment_status_maps_pnr_and_token(self):
        mapped = map_get_payment_status({"pnr": "abc123", "verification_token": "tok"})
        self.assertEqual(mapped["pnr"], "ABC123")  # normalized uppercase, same as other PNR mappers
        self.assertEqual(mapped["verification_token"], "tok")

    def test_create_booking_requires_at_least_one_passenger(self):
        with self.assertRaises(ArgumentMappingError):
            map_create_booking(
                {"quote_id": "q1", "passengers": [], "contact_email": "a@b.com", "contact_phone": "+491234567"},
                call_id="call_1",
            )

    def test_create_booking_requires_passenger_names(self):
        with self.assertRaises(ArgumentMappingError):
            map_create_booking(
                {
                    "quote_id": "q1",
                    "passengers": [{"first_name": "Ana"}],
                    "contact_email": "a@b.com",
                    "contact_phone": "+491234567",
                },
                call_id="call_1",
            )

    def test_create_booking_maps_contact_into_nested_dict(self):
        mapped = map_create_booking(
            {
                "quote_id": "q1",
                "passengers": [{"first_name": "Ana", "last_name": "Costa"}],
                "contact_email": "a@b.com",
                "contact_phone": "+491234567",
            },
            call_id="call_1",
        )
        self.assertEqual(mapped["contact"], {"email": "a@b.com", "phone": "+491234567"})
        self.assertEqual(mapped["passengers"][0]["passenger_type"], "adult")
        self.assertTrue(mapped["idempotency_key"].startswith("idem_"))

    def test_add_passenger_missing_name_raises(self):
        with self.assertRaises(ArgumentMappingError):
            map_add_passenger({"pnr": "ABC123", "verification_token": "tok", "first_name": "Ana"})


# ---------------------------------------------------------------------------
# Rate limiting: Vapi-specific keying policy (Phase 5.2)
# ---------------------------------------------------------------------------


class RateLimitKeyingTests(unittest.TestCase):
    def test_webhook_key_includes_source_ip(self):
        self.assertEqual(webhook_rate_limit_key("203.0.113.5"), "vapi_webhook:203.0.113.5")

    def test_webhook_key_falls_back_when_ip_unavailable(self):
        self.assertEqual(webhook_rate_limit_key(None), "vapi_webhook:unknown")

    def test_webhook_key_differs_by_ip(self):
        self.assertNotEqual(webhook_rate_limit_key("203.0.113.5"), webhook_rate_limit_key("203.0.113.6"))

    def test_tool_key_includes_call_id(self):
        self.assertEqual(tool_rate_limit_key("call_abc123"), "vapi_tool:call_abc123")

    def test_tool_key_differs_by_call(self):
        self.assertNotEqual(tool_rate_limit_key("call_1"), tool_rate_limit_key("call_2"))

    def test_tool_and_webhook_keys_cannot_collide(self):
        # Different prefixes ("vapi_webhook:" vs "vapi_tool:") guarantee
        # this even if the same raw value (an IP that happened to look
        # like a call_id, say) were passed to both — they share a
        # RateLimitStore's key namespace (see rate_limit_service.py), so
        # a collision here would mean one caller's tool-call volume could
        # exhaust a completely different caller's webhook-level budget.
        self.assertNotEqual(webhook_rate_limit_key("x"), tool_rate_limit_key("x"))


class VapiRateLimitProfileWiringTests(unittest.TestCase):
    """Confirms the actual infrastructure app/api/routes/vapi.py wires
    against — RATE_LIMIT_PROFILES' "vapi_webhook"/"vapi_tool" entries and
    BackoffLockout — behaves the way that (unexecuted) route assumes.
    This doesn't prove the FastAPI route itself works (it can't be
    imported here), but it does prove the assumptions it's built on
    aren't wrong, against the SAME dependency-free rate_limiter.py Phase
    4 already tested generically."""

    def test_vapi_webhook_profile_exists(self):
        limiter = build_rate_limiter("vapi_webhook", InMemoryRateLimitStore())
        self.assertIsNotNone(limiter)

    def test_vapi_tool_profile_exists(self):
        limiter = build_rate_limiter("vapi_tool", InMemoryRateLimitStore())
        self.assertIsNotNone(limiter)

    def test_vapi_webhook_limit_actually_triggers(self):
        store = InMemoryRateLimitStore()
        limiter = build_rate_limiter("vapi_webhook", store)
        key = webhook_rate_limit_key("203.0.113.5")
        results = [limiter.check(key, now=1000.0) for _ in range(200)]
        allowed_count = sum(1 for r in results if r.allowed)
        # RATE_LIMIT_PROFILES["vapi_webhook"] is (120, 60.0) as of this
        # phase — asserting "some requests got blocked" rather than the
        # exact number, so this test doesn't silently stop meaning
        # anything if that tuning value changes later without anyone
        # updating this test to match.
        self.assertLess(allowed_count, 200)
        self.assertGreater(allowed_count, 0)

    def test_vapi_tool_limit_is_independent_per_call(self):
        store = InMemoryRateLimitStore()
        limiter = build_rate_limiter("vapi_tool", store)
        # Exhaust call_1's budget.
        key1 = tool_rate_limit_key("call_1")
        for _ in range(200):
            limiter.check(key1, now=1000.0)
        # call_2 must be unaffected — this is the actual security-
        # relevant property (one runaway call can't starve every other
        # simultaneous caller of tool-execution budget).
        key2 = tool_rate_limit_key("call_2")
        result = limiter.check(key2, now=1000.0)
        self.assertTrue(result.allowed)

    def test_backoff_lockout_locks_after_threshold(self):
        # Mirrors what VerificationSessionService.submit() already does
        # internally with whatever BackoffLockout it's given (Phase 4,
        # tested generically) — this confirms the DEFAULT threshold used
        # by app.api.routes.vapi._verification_lockout() (BackoffLockout()
        # with no threshold override, so threshold=5) actually locks.
        lockout = BackoffLockout(InMemoryRateLimitStore())
        key = "verify:some-booking-id"
        for _ in range(5):
            lockout.record_failure(key, now=1000.0)
        self.assertFalse(lockout.is_locked(key, now=1000.0).allowed)

    def test_backoff_lockout_success_clears_failures(self):
        lockout = BackoffLockout(InMemoryRateLimitStore())
        key = "verify:some-booking-id"
        for _ in range(4):  # one under threshold
            lockout.record_failure(key, now=1000.0)
        lockout.record_success(key)
        # If record_success() truly reset the counter to zero (not just
        # "currently unlocked because we're under threshold"), this key
        # needs a FULL fresh threshold's worth of failures to lock again
        # — not just one more, which is what an uncleared count of 4
        # would need.
        for _ in range(4):
            lockout.record_failure(key, now=2000.0)
        self.assertTrue(lockout.is_locked(key, now=2000.0).allowed)
        lockout.record_failure(key, now=2000.0)  # 5th failure since the clear
        self.assertFalse(lockout.is_locked(key, now=2000.0).allowed)


if __name__ == "__main__":
    unittest.main()
