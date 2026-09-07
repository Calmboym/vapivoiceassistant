"""
Phase 6 Milestone 1 dependency-free tests for app/core/payments/*.py and
app/providers/payments/{base,mock}.py.

Runs the same way as tests/test_core_logic.py, tests/test_security_core.py,
and tests/test_vapi_core.py:

    python3 -m unittest tests.test_payments_core -v

No FastAPI/SQLAlchemy/Pydantic/`stripe` import anywhere in this file —
that's the point. app/services/payment_service.py (which DOES need
SQLAlchemy) is NOT tested here for the same reason
app/services/booking_service.py and cancellation_service.py aren't
tested in this suite either — see this milestone's handoff note,
"Testing status," for the honest accounting of what is and isn't
actually executed.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from app.core.payments.state_machine import (
    BOOKING_PAYMENT_STATUS_FOR_SESSION,
    BOOKING_PAYMENT_STATUSES_BLOCKING_NEW_SESSION,
    PAYMENT_SESSION_STATUSES,
    RELEVANT_WEBHOOK_EVENT_TYPES,
    TERMINAL_PAYMENT_SESSION_STATUSES,
    can_transition,
    is_terminal,
    new_status_for_webhook_event,
)
from app.providers.payments.base import (
    CheckoutSessionStatus,
    PaymentProviderError,
    PaymentSessionCreationError,
    PaymentSessionNotFoundError,
    WebhookVerificationError,
)
from app.providers.payments.mock import MOCK_VALID_SIGNATURE, MockPaymentProvider


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class StateMachineTests(unittest.TestCase):
    def test_every_status_has_a_booking_payment_status_mapping(self):
        missing = set(PAYMENT_SESSION_STATUSES) - set(BOOKING_PAYMENT_STATUS_FOR_SESSION)
        self.assertEqual(missing, set(), f"statuses with no Booking.payment_status mapping: {missing}")

    def test_booking_payment_status_mapping_never_produces_refunded(self):
        # REFUNDED is CancellationService's alone — see state_machine.py's
        # module docstring on why nothing in this milestone should ever
        # produce it.
        self.assertNotIn("REFUNDED", BOOKING_PAYMENT_STATUS_FOR_SESSION.values())

    def test_pending_can_reach_every_terminal_state_directly(self):
        for terminal in TERMINAL_PAYMENT_SESSION_STATUSES:
            self.assertTrue(can_transition("PENDING", terminal), f"PENDING -> {terminal} should be legal")

    def test_processing_can_only_reach_succeeded_or_failed(self):
        self.assertTrue(can_transition("PROCESSING", "SUCCEEDED"))
        self.assertTrue(can_transition("PROCESSING", "FAILED"))
        self.assertFalse(can_transition("PROCESSING", "EXPIRED"))
        self.assertFalse(can_transition("PROCESSING", "CANCELED"))

    def test_terminal_states_accept_no_further_transitions(self):
        for terminal in TERMINAL_PAYMENT_SESSION_STATUSES:
            for candidate in PAYMENT_SESSION_STATUSES:
                self.assertFalse(can_transition(terminal, candidate), f"{terminal} -> {candidate} should be illegal")

    def test_is_terminal_matches_the_frozenset(self):
        for status in PAYMENT_SESSION_STATUSES:
            self.assertEqual(is_terminal(status), status in TERMINAL_PAYMENT_SESSION_STATUSES)

    def test_unknown_status_is_not_a_legal_transition_target(self):
        self.assertFalse(can_transition("PENDING", "NOT_A_REAL_STATUS"))

    def test_blocking_statuses_are_exactly_pending_paid_refunded(self):
        self.assertEqual(BOOKING_PAYMENT_STATUSES_BLOCKING_NEW_SESSION, {"PENDING", "PAID", "REFUNDED"})


class WebhookEventMappingTests(unittest.TestCase):
    def test_completed_with_payment_paid_true_succeeds(self):
        self.assertEqual(new_status_for_webhook_event("checkout.session.completed", True), "SUCCEEDED")

    def test_completed_with_payment_paid_false_is_processing(self):
        # The async-payment-method case (§ stripe_provider.py docstring):
        # .completed fires but payment_status is still "unpaid".
        self.assertEqual(new_status_for_webhook_event("checkout.session.completed", False), "PROCESSING")

    def test_async_payment_succeeded_always_succeeds(self):
        self.assertEqual(new_status_for_webhook_event("checkout.session.async_payment_succeeded", False), "SUCCEEDED")

    def test_async_payment_failed_always_fails(self):
        # Confirms the case that motivated keying on event_type rather
        # than payment_paid alone: Stripe's own object still reads
        # payment_status="unpaid" (payment_paid=False) even on the
        # FAILURE event, since "unpaid" is the only non-paid value that
        # field ever takes — event_type is what actually distinguishes
        # "still processing" from "definitively failed."
        self.assertEqual(new_status_for_webhook_event("checkout.session.async_payment_failed", False), "FAILED")

    def test_expired_always_expires(self):
        self.assertEqual(new_status_for_webhook_event("checkout.session.expired", False), "EXPIRED")

    def test_unrecognized_event_type_returns_none(self):
        self.assertIsNone(new_status_for_webhook_event("payment_intent.succeeded", True))

    def test_relevant_event_types_matches_what_the_mapping_function_handles(self):
        for event_type in RELEVANT_WEBHOOK_EVENT_TYPES:
            self.assertIsNotNone(
                new_status_for_webhook_event(event_type, True),
                f"{event_type} is in RELEVANT_WEBHOOK_EVENT_TYPES but the mapping function returns None for it",
            )


# ---------------------------------------------------------------------------
# PaymentProviderError hierarchy
# ---------------------------------------------------------------------------


class PaymentProviderErrorTests(unittest.TestCase):
    def test_webhook_verification_error_is_not_retryable(self):
        # §9: retrying an invalid signature changes nothing — a route
        # must never treat this as "try again," only as a hard reject.
        exc = WebhookVerificationError()
        self.assertFalse(exc.retryable)
        self.assertEqual(exc.code, "WEBHOOK_SIGNATURE_INVALID")

    def test_session_creation_error_is_retryable(self):
        self.assertTrue(PaymentSessionCreationError().retryable)

    def test_session_not_found_is_not_retryable(self):
        self.assertFalse(PaymentSessionNotFoundError("cs_123").retryable)

    def test_all_payment_errors_are_payment_provider_errors(self):
        for exc in (WebhookVerificationError(), PaymentSessionCreationError(), PaymentSessionNotFoundError("x")):
            self.assertIsInstance(exc, PaymentProviderError)


# ---------------------------------------------------------------------------
# MockPaymentProvider
# ---------------------------------------------------------------------------


class MockPaymentProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = MockPaymentProvider()

    def _create(self, idempotency_key="idem_test_key_1", amount=Decimal("199.99"), currency="EUR"):
        return self.provider.create_checkout_session(
            reference="ABC123", amount=amount, currency=currency, idempotency_key=idempotency_key,
            success_url="https://example.com/success", cancel_url="https://example.com/cancel",
            metadata={"pnr": "ABC123"},
        )

    def test_create_session_returns_open_status(self):
        session = self._create()
        self.assertEqual(session.status, CheckoutSessionStatus.OPEN)
        self.assertTrue(session.checkout_url.startswith("https://"))

    def test_same_idempotency_key_returns_the_same_session(self):
        first = self._create(idempotency_key="idem_same")
        second = self._create(idempotency_key="idem_same")
        self.assertEqual(first.provider_session_id, second.provider_session_id)

    def test_different_idempotency_keys_produce_different_sessions(self):
        first = self._create(idempotency_key="idem_a")
        second = self._create(idempotency_key="idem_b")
        self.assertNotEqual(first.provider_session_id, second.provider_session_id)

    def test_session_id_is_deterministic_for_a_given_key(self):
        provider_a = MockPaymentProvider()
        provider_b = MockPaymentProvider()
        session_a = provider_a.create_checkout_session(
            reference="X", amount=Decimal("10.00"), currency="EUR", idempotency_key="idem_fixed",
            success_url="https://example.com/s", cancel_url="https://example.com/c", metadata={},
        )
        session_b = provider_b.create_checkout_session(
            reference="X", amount=Decimal("10.00"), currency="EUR", idempotency_key="idem_fixed",
            success_url="https://example.com/s", cancel_url="https://example.com/c", metadata={},
        )
        self.assertEqual(session_a.provider_session_id, session_b.provider_session_id)

    def test_get_session_status_before_completion_is_unpaid(self):
        session = self._create()
        status = self.provider.get_session_status(session.provider_session_id)
        self.assertFalse(status.payment_paid)
        self.assertEqual(status.status, CheckoutSessionStatus.OPEN)

    def test_get_status_for_unknown_session_raises(self):
        with self.assertRaises(PaymentSessionNotFoundError):
            self.provider.get_session_status("cs_does_not_exist")

    def test_simulate_completion_marks_paid(self):
        session = self._create()
        self.provider.simulate_completion(session.provider_session_id, paid=True)
        status = self.provider.get_session_status(session.provider_session_id)
        self.assertTrue(status.payment_paid)
        self.assertEqual(status.status, CheckoutSessionStatus.COMPLETE)

    def test_simulate_expiry_marks_expired(self):
        session = self._create()
        self.provider.simulate_expiry(session.provider_session_id)
        status = self.provider.get_session_status(session.provider_session_id)
        self.assertEqual(status.status, CheckoutSessionStatus.EXPIRED)

    # --- webhook verification ---

    def test_webhook_rejects_wrong_signature(self):
        session = self._create()
        payload = self.provider.build_webhook_event(
            event_id="evt_1", event_type="checkout.session.completed", provider_session_id=session.provider_session_id
        )
        with self.assertRaises(WebhookVerificationError):
            self.provider.verify_and_parse_webhook(payload, "wrong-signature")

    def test_webhook_rejects_missing_signature(self):
        session = self._create()
        payload = self.provider.build_webhook_event(
            event_id="evt_1", event_type="checkout.session.completed", provider_session_id=session.provider_session_id
        )
        with self.assertRaises(WebhookVerificationError):
            self.provider.verify_and_parse_webhook(payload, None)

    def test_webhook_accepts_correct_signature_and_parses_paid_event(self):
        session = self._create()
        self.provider.simulate_completion(session.provider_session_id, paid=True, payment_intent_id="pi_abc")
        payload = self.provider.build_webhook_event(
            event_id="evt_2", event_type="checkout.session.completed", provider_session_id=session.provider_session_id
        )
        event = self.provider.verify_and_parse_webhook(payload, MOCK_VALID_SIGNATURE)
        self.assertEqual(event.event_id, "evt_2")
        self.assertEqual(event.event_type, "checkout.session.completed")
        self.assertEqual(event.provider_session_id, session.provider_session_id)
        self.assertTrue(event.payment_paid)
        self.assertEqual(event.payment_intent_id, "pi_abc")

    def test_webhook_parses_unpaid_event_correctly(self):
        session = self._create()
        # Never called simulate_completion — still "unpaid" by default.
        payload = self.provider.build_webhook_event(
            event_id="evt_3", event_type="checkout.session.completed", provider_session_id=session.provider_session_id
        )
        event = self.provider.verify_and_parse_webhook(payload, MOCK_VALID_SIGNATURE)
        self.assertFalse(event.payment_paid)

    def test_webhook_rejects_malformed_payload_even_with_valid_signature(self):
        with self.assertRaises(WebhookVerificationError):
            self.provider.verify_and_parse_webhook(b"not json at all", MOCK_VALID_SIGNATURE)

    def test_full_lifecycle_end_to_end_via_mock(self):
        """Create -> simulate a customer paying -> verify the webhook
        PaymentService would receive maps to SUCCEEDED, without touching
        a database — the part of the Milestone 1 flow that CAN be proven
        end-to-end without SQLAlchemy/FastAPI installed."""
        session = self._create(idempotency_key="idem_lifecycle", amount=Decimal("450.00"), currency="USD")
        self.assertEqual(new_status_for_webhook_event("checkout.session.completed", False), "PROCESSING")

        self.provider.simulate_completion(session.provider_session_id, paid=True)
        payload = self.provider.build_webhook_event(
            event_id="evt_lifecycle", event_type="checkout.session.completed",
            provider_session_id=session.provider_session_id,
        )
        event = self.provider.verify_and_parse_webhook(payload, MOCK_VALID_SIGNATURE)
        new_status = new_status_for_webhook_event(event.event_type, event.payment_paid)
        self.assertEqual(new_status, "SUCCEEDED")
        self.assertTrue(can_transition("PENDING", new_status))
        self.assertEqual(BOOKING_PAYMENT_STATUS_FOR_SESSION[new_status], "PAID")


if __name__ == "__main__":
    unittest.main()
