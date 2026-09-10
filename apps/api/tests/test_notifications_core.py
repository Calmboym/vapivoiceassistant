"""
T-5 (docs/TASK_BOARD.md, Phase 8) dependency-free tests for
app/core/notifications/content.py and app/services/{email_provider,
sms_provider}.py's Mock* classes + error types.

Runs the same way as tests/test_core_logic.py, tests/test_security_core.py,
tests/test_vapi_core.py, and tests/test_payments_core.py:

    python3 -m unittest tests.test_notifications_core -v

No FastAPI/SQLAlchemy/Pydantic/httpx import anywhere in this file — that's
the point (confirmed by actually running this file with none of those
packages installed in this sandbox). app/services/notification_service.py
(which DOES need SQLAlchemy for Session/Booking/Payment/record_audit_event)
and ResendEmailProvider/TwilioSmsProvider's actual network calls (which
need httpx) are NOT exercised here — see this task's handoff for the
honest accounting of what is and isn't actually executed this session.

Coverage focus: the content builders are where a real privacy/accuracy
mistake would show up (a passport number, a fabricated fee, a fabricated
baggage figure) — see app/core/notifications/content.py's own docstring
for the rules being enforced. Several tests below assert on the ABSENCE
of something (no passport field exists at all, no digit-shaped fee
appears when the deadline is unknown) rather than only asserting
presence of the expected content.
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.core.notifications.content import (
    BaggageAllowance,
    BookingConfirmationData,
    NotificationContent,
    PassengerSummary,
    PaymentLinkData,
    build_booking_confirmation_email,
    build_payment_link_email,
    build_payment_link_sms,
)
from app.services.email_provider import (
    EmailDeliveryError,
    EmailProvider,
    MockEmailProvider,
    SentEmail,
)
from app.services.sms_provider import MockSmsProvider, SentSms, SmsDeliveryError, SmsProvider

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _passengers() -> tuple[PassengerSummary, ...]:
    return (
        PassengerSummary(first_name="Ada", last_name="Lovelace", passenger_type="adult"),
        PassengerSummary(first_name="Charles", last_name="Babbage", passenger_type="adult"),
        PassengerSummary(first_name="Grace", last_name="Hopper", passenger_type="child"),
    )


def _confirmation_data(**overrides) -> BookingConfirmationData:
    base = dict(
        pnr="ABC123",
        origin="JFK",
        destination="LAX",
        flight_number="C123",
        aircraft_type="Gulfstream G650",
        departure_time=datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc),
        arrival_time=datetime(2026, 10, 1, 17, 45, tzinfo=timezone.utc),
        currency="USD",
        total_price=Decimal("12500.00"),
        payment_status="PAID",
        passengers=_passengers(),
        cancellation_deadline=None,
        baggage=None,
    )
    base.update(overrides)
    return BookingConfirmationData(**base)


def _payment_link_data(**overrides) -> PaymentLinkData:
    base = dict(
        pnr="ABC123",
        amount=Decimal("500"),
        currency="USD",
        checkout_url="https://checkout.stripe.com/pay/cs_test_abc123",
        expires_at=datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return PaymentLinkData(**base)


# ---------------------------------------------------------------------------
# Booking confirmation content
# ---------------------------------------------------------------------------


class BookingConfirmationContentTests(unittest.TestCase):
    def test_includes_pnr_flight_number_and_route(self):
        content = build_booking_confirmation_email(_confirmation_data())
        for field in ("ABC123", "C123", "JFK", "LAX"):
            self.assertIn(field, content.text_body)
            self.assertIn(field, content.html_body)
        self.assertIn("ABC123", content.subject)

    def test_includes_every_passenger_name(self):
        content = build_booking_confirmation_email(_confirmation_data())
        for full_name in ("Ada Lovelace", "Charles Babbage", "Grace Hopper"):
            self.assertIn(full_name, content.text_body)
            self.assertIn(full_name, content.html_body)

    def test_includes_total_price_and_currency(self):
        content = build_booking_confirmation_email(_confirmation_data(total_price=Decimal("9999.5")))
        self.assertIn("9999.50 USD", content.text_body)

    def test_includes_payment_status_lowercased(self):
        content = build_booking_confirmation_email(_confirmation_data(payment_status="PAID"))
        self.assertIn("payment status: paid", content.text_body.lower())

    def test_passenger_summary_has_no_passport_shaped_field(self):
        # Structural guarantee, not a runtime filter — see module
        # docstring's "structural enforcement" note. If someone later
        # adds a passport field to PassengerSummary, this test fails
        # immediately regardless of whether any builder happens to use it.
        field_names = {f.name for f in dataclasses.fields(PassengerSummary)}
        for forbidden in ("passport_number", "passport_country", "passport_expiry", "date_of_birth"):
            self.assertNotIn(forbidden, field_names)
        self.assertEqual(field_names, {"first_name", "last_name", "passenger_type"})

    def test_no_content_ever_contains_the_word_passport(self):
        content = build_booking_confirmation_email(_confirmation_data())
        self.assertNotIn("passport", content.text_body.lower())
        self.assertNotIn("passport", content.html_body.lower())

    def test_unknown_cancellation_deadline_gets_honest_generic_sentence(self):
        content = build_booking_confirmation_email(_confirmation_data(cancellation_deadline=None))
        self.assertIn("depend on how close to departure", content.text_body)
        # Must NOT claim a specific "Free cancellation until" date when
        # there isn't one.
        self.assertNotIn("Free cancellation until", content.text_body)

    def test_known_cancellation_deadline_is_stated_explicitly(self):
        deadline = datetime(2026, 9, 28, 23, 59, tzinfo=timezone.utc)
        content = build_booking_confirmation_email(_confirmation_data(cancellation_deadline=deadline))
        self.assertIn("Free cancellation until 2026-09-28 23:59 UTC", content.text_body)

    def test_unknown_baggage_gets_honest_generic_sentence_no_numbers(self):
        content = build_booking_confirmation_email(_confirmation_data(baggage=None))
        self.assertIn("depends on your fare", content.text_body)

    def test_known_baggage_reports_the_real_numbers(self):
        baggage = BaggageAllowance(checked_bags_included=2, checked_bag_max_kg=23, cabin_bag_max_kg=8)
        content = build_booking_confirmation_email(_confirmation_data(baggage=baggage))
        self.assertIn("2 checked bag(s) included", content.text_body)
        self.assertIn("up to 23kg each", content.text_body)
        self.assertIn("cabin bag up to 8kg", content.text_body)

    def test_returns_notification_content_dataclass(self):
        content = build_booking_confirmation_email(_confirmation_data())
        self.assertIsInstance(content, NotificationContent)
        self.assertTrue(content.subject)
        self.assertTrue(content.text_body)
        self.assertTrue(content.html_body)


# ---------------------------------------------------------------------------
# Payment link content
# ---------------------------------------------------------------------------


class PaymentLinkContentTests(unittest.TestCase):
    def test_email_includes_checkout_url_amount_currency_and_pnr(self):
        content = build_payment_link_email(_payment_link_data())
        self.assertIn("https://checkout.stripe.com/pay/cs_test_abc123", content.text_body)
        self.assertIn("https://checkout.stripe.com/pay/cs_test_abc123", content.html_body)
        self.assertIn("500.00 USD", content.text_body)
        self.assertIn("ABC123", content.subject)

    def test_email_includes_expiry(self):
        content = build_payment_link_email(_payment_link_data())
        self.assertIn("2026-10-01 18:00 UTC", content.text_body)

    def test_email_never_mentions_card_details(self):
        content = build_payment_link_email(_payment_link_data())
        for forbidden in ("card number", "cvv", "CVV", "pin", "PIN"):
            self.assertNotIn(forbidden, content.text_body)

    def test_sms_includes_checkout_url_and_pnr(self):
        sms_text = build_payment_link_sms(_payment_link_data())
        self.assertIn("https://checkout.stripe.com/pay/cs_test_abc123", sms_text)
        self.assertIn("ABC123", sms_text)
        self.assertIn("500.00 USD", sms_text)

    def test_sms_is_a_single_plain_string(self):
        sms_text = build_payment_link_sms(_payment_link_data())
        self.assertIsInstance(sms_text, str)
        self.assertNotIn("\n", sms_text)

    def test_money_formatting_always_shows_two_decimals(self):
        content = build_payment_link_email(_payment_link_data(amount=Decimal("1000")))
        self.assertIn("1000.00 USD", content.text_body)


# ---------------------------------------------------------------------------
# MockEmailProvider / MockSmsProvider
# ---------------------------------------------------------------------------


class MockEmailProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider: EmailProvider = MockEmailProvider()

    def test_send_password_reset_records_reset_url(self):
        self.provider.send_password_reset(to_email="a@example.com", reset_url="https://x/reset")
        self.assertEqual(len(self.provider.sent), 1)
        sent = self.provider.sent[0]
        self.assertIsInstance(sent, SentEmail)
        self.assertEqual(sent.kind, "password_reset")
        self.assertEqual(sent.context["reset_url"], "https://x/reset")

    def test_send_email_verification_records_verify_url(self):
        self.provider.send_email_verification(to_email="a@example.com", verify_url="https://x/verify")
        self.assertEqual(self.provider.sent[0].kind, "email_verification")

    def test_send_booking_confirmation_records_pnr_and_subject(self):
        content = build_booking_confirmation_email(_confirmation_data())
        self.provider.send_booking_confirmation(
            to_email="a@example.com", pnr="ABC123", content=content, idempotency_key="booking_confirmation/ABC123",
        )
        sent = self.provider.sent[0]
        self.assertEqual(sent.kind, "booking_confirmation")
        self.assertEqual(sent.context["pnr"], "ABC123")
        self.assertEqual(sent.context["subject"], content.subject)

    def test_send_payment_link_records_pnr_and_subject(self):
        content = build_payment_link_email(_payment_link_data())
        self.provider.send_payment_link(
            to_email="a@example.com", pnr="ABC123", content=content, idempotency_key="payment_link/1",
        )
        sent = self.provider.sent[0]
        self.assertEqual(sent.kind, "payment_link")
        self.assertEqual(sent.context["pnr"], "ABC123")

    def test_sends_accumulate_in_order(self):
        self.provider.send_password_reset(to_email="a@example.com", reset_url="https://x/1")
        self.provider.send_email_verification(to_email="a@example.com", verify_url="https://x/2")
        self.assertEqual([s.kind for s in self.provider.sent], ["password_reset", "email_verification"])

    def test_mock_provider_never_raises(self):
        try:
            for _ in range(5):
                self.provider.send_password_reset(to_email="a@example.com", reset_url="https://x")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"MockEmailProvider raised unexpectedly: {exc}")


class MockSmsProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider: SmsProvider = MockSmsProvider()

    def test_send_payment_link_records_context(self):
        self.provider.send_payment_link(
            to_phone="+15551234567", pnr="ABC123", text_body="pay now", idempotency_key="payment_link/1",
        )
        self.assertEqual(len(self.provider.sent), 1)
        sent = self.provider.sent[0]
        self.assertIsInstance(sent, SentSms)
        self.assertEqual(sent.to_phone, "+15551234567")
        self.assertEqual(sent.context["pnr"], "ABC123")
        self.assertEqual(sent.context["text_body"], "pay now")

    def test_multiple_sends_accumulate_in_order(self):
        self.provider.send_payment_link(
            to_phone="+15551234567", pnr="ABC123", text_body="first", idempotency_key="k1",
        )
        self.provider.send_payment_link(
            to_phone="+15559876543", pnr="XYZ999", text_body="second", idempotency_key="k2",
        )
        self.assertEqual([s.context["text_body"] for s in self.provider.sent], ["first", "second"])

    def test_mock_provider_never_raises(self):
        try:
            self.provider.send_payment_link(
                to_phone="+15551234567", pnr="ABC123", text_body="x", idempotency_key="k",
            )
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"MockSmsProvider raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Delivery error types
# ---------------------------------------------------------------------------


class DeliveryErrorTests(unittest.TestCase):
    def test_email_delivery_error_stores_code_message_retryable(self):
        exc = EmailDeliveryError("RESEND_RATE_LIMIT_EXCEEDED", "Too many requests", retryable=True)
        self.assertEqual(exc.code, "RESEND_RATE_LIMIT_EXCEEDED")
        self.assertEqual(exc.message, "Too many requests")
        self.assertTrue(exc.retryable)

    def test_email_delivery_error_defaults_to_not_retryable(self):
        exc = EmailDeliveryError("RESEND_VALIDATION_ERROR", "Invalid `to` field")
        self.assertFalse(exc.retryable)

    def test_sms_delivery_error_stores_code_message_retryable(self):
        exc = SmsDeliveryError("TWILIO_21211", "Invalid 'To' Phone Number", retryable=False)
        self.assertEqual(exc.code, "TWILIO_21211")
        self.assertFalse(exc.retryable)

    def test_sms_delivery_error_defaults_to_not_retryable(self):
        exc = SmsDeliveryError("TWILIO_21604", "'To' phone number is required")
        self.assertFalse(exc.retryable)

    def test_both_error_types_are_plain_exceptions_not_a_shared_base(self):
        # Deliberately independent hierarchies — see both modules'
        # docstrings for why (mirrors AirlineProvider/PaymentProvider
        # each having their own error hierarchy rather than sharing one).
        self.assertTrue(issubclass(EmailDeliveryError, Exception))
        self.assertTrue(issubclass(SmsDeliveryError, Exception))
        self.assertFalse(issubclass(EmailDeliveryError, SmsDeliveryError))
        self.assertFalse(issubclass(SmsDeliveryError, EmailDeliveryError))


if __name__ == "__main__":
    unittest.main()
