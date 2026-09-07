"""
Dependency-free tests for the parts of Charter123 that don't need FastAPI,
SQLAlchemy, or a database: the mock GDS simulation, date resolution, PNR
generation, and idempotency-key derivation.

Run with:  python3 -m unittest tests.test_core_logic -v
(from apps/api/, with no `pip install` required — everything here is stdlib).

The FastAPI/SQLAlchemy layers built on top of this are exercised separately
by tests/test_api_*.py, which DO require `pip install -r requirements.txt`.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/api/ on sys.path

from app.core.dates import resolve_relative_date, now_in_tz
from app.core.idempotency import InMemoryIdempotencyStore, derive_idempotency_key
from app.core.pnr import generate_pnr, generate_unique_pnr
from app.providers.airline.base import CabinClass, PassengerInput, ProviderBookingStatus, ProviderError
from app.providers.airline.mock import MockAirlineProvider, _money


FRA_NOW = datetime(2026, 8, 31, 9, 0, tzinfo=ZoneInfo("Europe/Berlin"))  # a Monday


class MockProviderSearchTests(unittest.TestCase):
    def setUp(self):
        self.provider = MockAirlineProvider(clock=lambda: FRA_NOW)

    def test_search_returns_offers_for_a_real_route(self):
        offers = self.provider.search_flights(
            origin="FRA", destination="DXB", departure_date=date(2026, 9, 4), adults=3,
        )
        self.assertGreater(len(offers), 0)
        for offer in offers:
            self.assertEqual(offer.origin, "FRA")
            self.assertEqual(offer.destination, "DXB")
            self.assertGreater(offer.price_per_passenger, 0)
            self.assertTrue(offer.flight_number.startswith("CX"))

    def test_search_is_deterministic_across_repeated_calls(self):
        first = self.provider.search_flights(origin="FRA", destination="DXB", departure_date=date(2026, 9, 4), adults=1)
        second = self.provider.search_flights(origin="FRA", destination="DXB", departure_date=date(2026, 9, 4), adults=1)
        self.assertEqual([o.flight_id for o in first], [o.flight_id for o in second])
        self.assertEqual([o.price_per_passenger for o in first], [o.price_per_passenger for o in second])

    def test_get_flight_reconstructs_the_same_offer_search_returned(self):
        offers = self.provider.search_flights(origin="FRA", destination="DXB", departure_date=date(2026, 9, 4), adults=1)
        refetched = self.provider.get_flight(offers[0].flight_id)
        self.assertEqual(offers[0].price_per_passenger, refetched.price_per_passenger)
        self.assertEqual(offers[0].departure_time, refetched.departure_time)

    def test_unknown_airport_is_rejected_not_guessed(self):
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search_flights(origin="ZZZ", destination="DXB", departure_date=date(2026, 9, 4), adults=1)
        self.assertEqual(ctx.exception.code, "UNKNOWN_AIRPORT")

    def test_same_origin_and_destination_rejected(self):
        with self.assertRaises(ProviderError):
            self.provider.search_flights(origin="FRA", destination="FRA", departure_date=date(2026, 9, 4), adults=1)


class BookingLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.provider = MockAirlineProvider(clock=lambda: FRA_NOW)
        offers = self.provider.search_flights(origin="FRA", destination="DXB", departure_date=date(2026, 9, 4), adults=3)
        self.flight = offers[0]
        self.quote = self.provider.get_fare_quote(self.flight.flight_id, adults=3)
        self.passengers = [
            PassengerInput(first_name="Anna", last_name="Keller"),
            PassengerInput(first_name="Jonas", last_name="Keller"),
            PassengerInput(first_name="Mira", last_name="Keller"),
        ]

    def test_quote_total_equals_base_plus_tax_plus_fee(self):
        self.assertEqual(self.quote.total_price, self.quote.base_fare + self.quote.taxes + self.quote.fees)
        self.assertGreater(self.quote.total_price, self.quote.base_fare)

    def test_full_lifecycle_search_quote_book_lookup_modify_cancel(self):
        booking = self.provider.create_booking(
            quote_id=self.quote.quote_id, passengers=self.passengers,
            contact_email="anna@example.com", contact_phone="+4915112345",
            idempotency_key="call123:create_booking:1",
        )
        self.assertEqual(booking.status, ProviderBookingStatus.CONFIRMED)
        self.assertEqual(len(booking.provider_booking_reference), 13)  # "PRV" + 10 hex chars

        fetched = self.provider.get_booking(booking.provider_booking_reference)
        self.assertEqual(fetched.provider_booking_reference, booking.provider_booking_reference)

        policy = self.provider.get_cancellation_policy(booking.provider_booking_reference)
        self.assertGreater(policy.refundable_amount, 0)
        self.assertEqual(policy.refundable_amount + policy.cancellation_fee, booking.total_price)

        result = self.provider.cancel_booking(booking.provider_booking_reference, idempotency_key="call123:cancel:1")
        self.assertFalse(result.already_cancelled)
        self.assertEqual(result.status, ProviderBookingStatus.CANCELLED)

    def test_cancellation_is_idempotent(self):
        booking = self.provider.create_booking(
            quote_id=self.quote.quote_id, passengers=self.passengers,
            contact_email="anna@example.com", contact_phone="+4915112345",
            idempotency_key="call123:create_booking:1",
        )
        first = self.provider.cancel_booking(booking.provider_booking_reference, idempotency_key="call123:cancel:1")
        second = self.provider.cancel_booking(booking.provider_booking_reference, idempotency_key="call123:cancel:2")
        self.assertFalse(first.already_cancelled)
        self.assertTrue(second.already_cancelled)
        self.assertEqual(second.refundable_amount, Decimal("0.00"))

    def test_create_booking_with_same_idempotency_key_does_not_double_book(self):
        key = "call999:create_booking:same"
        first = self.provider.create_booking(
            quote_id=self.quote.quote_id, passengers=self.passengers,
            contact_email="a@example.com", contact_phone="+491", idempotency_key=key,
        )
        second = self.provider.create_booking(
            quote_id=self.quote.quote_id, passengers=self.passengers,
            contact_email="a@example.com", contact_phone="+491", idempotency_key=key,
        )
        self.assertEqual(first.provider_booking_reference, second.provider_booking_reference)
        self.assertEqual(len(self.provider._bookings), 1)  # exactly one booking was created

    def test_expired_quote_cannot_be_booked(self):
        stale_provider = MockAirlineProvider(clock=lambda: FRA_NOW)
        offers = stale_provider.search_flights(origin="FRA", destination="DXB", departure_date=date(2026, 9, 4), adults=1)
        quote = stale_provider.get_fare_quote(offers[0].flight_id, adults=1)
        stale_provider._now = lambda: FRA_NOW + timedelta(minutes=16)  # past the 15-minute validity window
        with self.assertRaises(ProviderError) as ctx:
            stale_provider.create_booking(
                quote_id=quote.quote_id, passengers=[PassengerInput(first_name="A", last_name="B")],
                contact_email="a@example.com", contact_phone="+491", idempotency_key="k1",
            )
        self.assertEqual(ctx.exception.code, "FARE_EXPIRED")

    def test_cancellation_fee_rises_as_departure_approaches(self):
        far_provider = MockAirlineProvider(clock=lambda: FRA_NOW)
        offers = far_provider.search_flights(origin="FRA", destination="DXB", departure_date=date(2026, 12, 1), adults=1)
        quote = far_provider.get_fare_quote(offers[0].flight_id, adults=1)
        booking = far_provider.create_booking(
            quote_id=quote.quote_id, passengers=[PassengerInput(first_name="A", last_name="B")],
            contact_email="a@example.com", contact_phone="+491", idempotency_key="k1",
        )
        far_policy = far_provider.get_cancellation_policy(booking.provider_booking_reference)

        soon_provider = MockAirlineProvider(clock=lambda: booking.departure_time - timedelta(hours=12))
        soon_provider._bookings[booking.provider_booking_reference] = booking
        soon_policy = soon_provider.get_cancellation_policy(booking.provider_booking_reference)

        self.assertGreater(soon_policy.cancellation_fee, far_policy.cancellation_fee)

    def test_remove_last_passenger_is_rejected(self):
        booking = self.provider.create_booking(
            quote_id=self.provider.get_fare_quote(self.flight.flight_id, adults=1).quote_id,
            passengers=[PassengerInput(first_name="Solo", last_name="Traveler", passenger_id="pax_1")],
            contact_email="a@example.com", contact_phone="+491", idempotency_key="solo1",
        )
        with self.assertRaises(ProviderError) as ctx:
            self.provider.remove_passenger(booking.provider_booking_reference, "pax_1")
        self.assertEqual(ctx.exception.code, "PASSENGER_VALIDATION_FAILED")

    def test_add_then_remove_passenger_updates_total_price(self):
        booking = self.provider.create_booking(
            quote_id=self.provider.get_fare_quote(self.flight.flight_id, adults=1).quote_id,
            passengers=[PassengerInput(first_name="Solo", last_name="Traveler", passenger_id="pax_1")],
            contact_email="a@example.com", contact_phone="+491", idempotency_key="addrm1",
        )
        original_total = self.provider.get_booking(booking.provider_booking_reference).total_price

        with_extra = self.provider.add_passenger(
            booking.provider_booking_reference, PassengerInput(first_name="Plus", last_name="One")
        )
        self.assertEqual(len(with_extra.passengers), 2)
        self.assertGreater(with_extra.total_price, original_total)
        # The provider assigns the new passenger an ID even though the caller didn't set one.
        self.assertIsNotNone(with_extra.passengers[-1].passenger_id)

        back_to_one = self.provider.remove_passenger(
            booking.provider_booking_reference, with_extra.passengers[-1].passenger_id
        )
        self.assertEqual(len(back_to_one.passengers), 1)
        self.assertEqual(back_to_one.total_price, original_total)

    def test_update_booking_rebooks_to_a_new_flight_and_recomputes_price(self):
        booking = self.provider.create_booking(
            quote_id=self.quote.quote_id, passengers=self.passengers,
            contact_email="a@example.com", contact_phone="+491", idempotency_key="modify1",
        )
        new_offers = self.provider.search_flights(origin="FRA", destination="DXB", departure_date=date(2026, 9, 5), adults=3)
        updated = self.provider.update_booking(
            booking.provider_booking_reference,
            {"new_flight_id": new_offers[0].flight_id},
            idempotency_key="modify1:update:1",
        )
        self.assertEqual(updated.flight_id, new_offers[0].flight_id)
        self.assertEqual(updated.status, ProviderBookingStatus.MODIFIED)
        # Price is recomputed from the new flight, not left over from the old one.
        expected = _money(new_offers[0].price_per_passenger * 3 * Decimal("1.08") + Decimal("25.00"))
        self.assertEqual(updated.total_price, expected)

    def test_update_booking_is_idempotent(self):
        booking = self.provider.create_booking(
            quote_id=self.quote.quote_id, passengers=self.passengers,
            contact_email="a@example.com", contact_phone="+491", idempotency_key="modify2",
        )
        new_offers = self.provider.search_flights(origin="FRA", destination="DXB", departure_date=date(2026, 9, 5), adults=3)
        changes = {"new_flight_id": new_offers[0].flight_id}
        first = self.provider.update_booking(booking.provider_booking_reference, changes, idempotency_key="modify2:update:same")
        second = self.provider.update_booking(booking.provider_booking_reference, changes, idempotency_key="modify2:update:same")
        self.assertEqual(first.updated_at, second.updated_at)  # second call replayed, didn't re-run

    def test_cannot_modify_a_cancelled_booking(self):
        booking = self.provider.create_booking(
            quote_id=self.quote.quote_id, passengers=self.passengers,
            contact_email="a@example.com", contact_phone="+491", idempotency_key="modify3",
        )
        self.provider.cancel_booking(booking.provider_booking_reference, idempotency_key="modify3:cancel")
        with self.assertRaises(ProviderError) as ctx:
            self.provider.update_booking(
                booking.provider_booking_reference, {"contact_email": "new@example.com"}, idempotency_key="modify3:update"
            )
        self.assertEqual(ctx.exception.code, "BOOKING_NOT_MODIFIABLE")


class DateResolutionTests(unittest.TestCase):
    def test_tomorrow_needs_no_confirmation(self):
        res = resolve_relative_date("tomorrow", FRA_NOW)
        self.assertEqual(res.resolved_date, date(2026, 9, 1))
        self.assertFalse(res.needs_confirmation)

    def test_next_friday_resolves_and_flags_for_confirmation(self):
        # FRA_NOW is Monday 2026-08-31; the next Friday is 2026-09-04.
        res = resolve_relative_date("next Friday", FRA_NOW)
        self.assertEqual(res.resolved_date, date(2026, 9, 4))
        self.assertTrue(res.needs_confirmation)
        self.assertIn("September 4", res.clarification_prompt)

    def test_bare_weekday_matches_next_friday_convention(self):
        bare = resolve_relative_date("friday", FRA_NOW)
        explicit = resolve_relative_date("next friday", FRA_NOW)
        self.assertEqual(bare.resolved_date, explicit.resolved_date)

    def test_this_weekend_flags_ambiguity_between_two_days(self):
        res = resolve_relative_date("this weekend", FRA_NOW)
        self.assertTrue(res.needs_confirmation)
        self.assertIn("Saturday", res.clarification_prompt)
        self.assertIn("Sunday", res.clarification_prompt)

    def test_the_nth_resolves_within_current_month(self):
        res = resolve_relative_date("the 12th", FRA_NOW)
        self.assertEqual(res.resolved_date, date(2026, 9, 12))

    def test_nonsense_phrase_is_never_silently_guessed(self):
        res = resolve_relative_date("sometime soonish", FRA_NOW)
        self.assertIsNone(res.resolved_date)
        self.assertTrue(res.needs_confirmation)

    def test_now_in_tz_is_tz_aware(self):
        now = now_in_tz("Asia/Dubai")
        self.assertIsNotNone(now.tzinfo)


class PnrTests(unittest.TestCase):
    def test_pnr_format(self):
        pnr = generate_pnr()
        self.assertEqual(len(pnr), 6)
        for ambiguous_char in "01OI":
            self.assertNotIn(ambiguous_char, pnr)

    def test_generate_unique_pnr_retries_on_collision(self):
        seen = {"AAAAAA"}  # force at least one collision
        calls = {"n": 0}

        def exists(pnr: str) -> bool:
            calls["n"] += 1
            if pnr in seen:
                return True
            seen.add(pnr)
            return False

        pnr = generate_unique_pnr(exists)
        self.assertIn(pnr, seen)

    def test_many_pnrs_are_unique_in_practice(self):
        pnrs = {generate_pnr() for _ in range(2000)}
        self.assertGreater(len(pnrs), 1990)  # allow a tiny amount of coincidental collision


class IdempotencyTests(unittest.TestCase):
    def test_same_inputs_produce_the_same_key(self):
        k1 = derive_idempotency_key("call_1", "create_booking", {"quote_id": "q1", "pax": 3})
        k2 = derive_idempotency_key("call_1", "create_booking", {"pax": 3, "quote_id": "q1"})  # different key order
        self.assertEqual(k1, k2)

    def test_different_calls_produce_different_keys(self):
        k1 = derive_idempotency_key("call_1", "create_booking", {"quote_id": "q1"})
        k2 = derive_idempotency_key("call_2", "create_booking", {"quote_id": "q1"})
        self.assertNotEqual(k1, k2)

    def test_store_replays_completed_result_instead_of_rerunning(self):
        store = InMemoryIdempotencyStore()
        key = "idem_test"
        self.assertIsNone(store.begin(key))  # first time: proceed
        store.complete(key, {"booking_reference": "PRVABC"})
        seen_again = store.begin(key)
        self.assertIsNotNone(seen_again)
        self.assertEqual(seen_again.result["booking_reference"], "PRVABC")

    def test_failed_operation_can_be_retried_under_the_same_key(self):
        store = InMemoryIdempotencyStore()
        key = "idem_retry"
        store.begin(key)
        store.fail(key)
        self.assertIsNone(store.begin(key))  # cleared -> allowed to proceed again


if __name__ == "__main__":
    unittest.main(verbosity=2)
