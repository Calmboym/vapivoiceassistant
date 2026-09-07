"""
MockAirlineProvider — realistic, fully-functional stand-in for a real
GDS/airline API. Required per MASTER BUILD PROMPT §39: the whole system must
run in MOCK mode with zero external aviation credentials.

Design choices worth knowing:

* Flight generation is a *pure function* of (origin, destination, date,
  index) via a seeded RNG. That means search_flights(...) and a later
  get_flight(flight_id) always agree on the same flight's details without
  needing a shared database — the flight_id itself encodes the seed. This
  mirrors how a real airline's schedule is stable, not randomly re-rolled
  on every lookup.
* Quotes and bookings, by contrast, genuinely need memory (a quote expires,
  a booking gets modified) — those live in the instance's in-memory
  `_quotes` / `_bookings` dicts. That's appropriate for MOCK mode; it is
  explicitly *not* how the real application's own booking data is stored
  (that's PostgreSQL, via app/models/booking.py — see docs/AIRLINE_PROVIDER.md).
* Zero third-party imports. This file can be unit-tested with nothing but
  the standard library, which is exactly what tests/test_core_logic.py does.
"""

from __future__ import annotations

import math
import random
import threading
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from app.providers.airline.base import (
    AirlineProvider,
    Aircraft,
    BaggageRules,
    BookingNotFoundError,
    CabinClass,
    CancellationPolicy,
    CancellationResult,
    FareQuote,
    FareRules,
    FlightNotFoundError,
    FlightOffer,
    PassengerInput,
    ProviderBooking,
    ProviderBookingStatus,
    ProviderCapabilities,
    ProviderError,
)
from app.providers.airline.reference_data import AIRPORTS, FLEET, base_price_for_route

_TAX_RATE = Decimal("0.08")
_BOOKING_FEE = Decimal("25.00")
_PASSENGER_WEIGHT = {"adult": Decimal("1.0"), "child": Decimal("0.75"), "infant": Decimal("0.10")}
_QUOTE_VALIDITY_MINUTES = 15


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class MockAirlineProvider(AirlineProvider):
    def __init__(self, *, clock: callable = None) -> None:
        self._now = clock or (lambda: datetime.now(ZoneInfo("UTC")))
        self._lock = threading.Lock()
        self._quotes: dict[str, tuple[FareQuote, "FlightOffer"]] = {}
        self._bookings: dict[str, ProviderBooking] = {}
        self._idempotency_seen: dict[str, str] = {}  # idempotency_key -> booking_reference

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_hold_booking=True,
            supports_payment=True,
            supports_cancellation=True,
            supports_modification=True,
            supports_seat_selection=False,
            supports_baggage=True,
            supports_charter=True,
            supports_passenger_updates=True,
        )

    # ---------------------------------------------------------------- search

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        adults: int,
        children: int = 0,
        infants: int = 0,
        cabin_class: CabinClass = CabinClass.ECONOMY,
        return_date: date | None = None,
        direct_only: bool = False,
        max_results: int = 6,
    ) -> list[FlightOffer]:
        if origin not in AIRPORTS:
            raise ProviderError("UNKNOWN_AIRPORT", f"Unknown origin airport: {origin}")
        if destination not in AIRPORTS:
            raise ProviderError("UNKNOWN_AIRPORT", f"Unknown destination airport: {destination}")
        if origin == destination:
            raise ProviderError("INVALID_ROUTE", "Origin and destination must differ")

        count = min(max_results, 4)
        offers = [
            self._generate_flight(origin, destination, departure_date, i, cabin_class)
            for i in range(count)
        ]
        return offers

    def get_flight(self, flight_id: str) -> FlightOffer:
        parsed = _parse_flight_id(flight_id)
        if parsed is None:
            raise FlightNotFoundError(flight_id)
        origin, destination, dep_date, index, cabin_class = parsed
        if origin not in AIRPORTS or destination not in AIRPORTS:
            raise FlightNotFoundError(flight_id)
        return self._generate_flight(origin, destination, dep_date, index, cabin_class)

    def _generate_flight(
        self, origin: str, destination: str, departure_date: date, index: int, cabin_class: CabinClass
    ) -> FlightOffer:
        flight_id = _make_flight_id(origin, destination, departure_date, index, cabin_class)
        seed = f"{origin}-{destination}-{departure_date.isoformat()}-{index}"
        rng = random.Random(seed)

        origin_ap = AIRPORTS[origin]
        dest_ap = AIRPORTS[destination]

        # Spread offers through the day: roughly 06:00, 10:30, 15:00, 19:30 local.
        base_hour = 6 + index * 4
        dep_naive = datetime(
            departure_date.year, departure_date.month, departure_date.day,
            min(base_hour, 22), rng.choice([0, 15, 30, 45]),
        )
        departure_time = dep_naive.replace(tzinfo=ZoneInfo(origin_ap.timezone))

        duration_minutes = _estimate_duration_minutes(origin_ap, dest_ap, rng)
        arrival_time = (departure_time.astimezone(ZoneInfo("UTC")) + timedelta(minutes=duration_minutes)).astimezone(
            ZoneInfo(dest_ap.timezone)
        )

        aircraft_template = rng.choice([a for a in FLEET if a.category == "commercial"])
        available_seats = rng.randint(4, min(40, aircraft_template.seat_capacity))
        aircraft = replace(aircraft_template, available_seats=available_seats, current_location=origin)

        base = base_price_for_route(origin, destination)
        jitter = rng.uniform(0.85, 1.25)
        cabin_multiplier = {
            CabinClass.ECONOMY: Decimal("1.0"),
            CabinClass.PREMIUM_ECONOMY: Decimal("1.6"),
            CabinClass.BUSINESS: Decimal("3.2"),
            CabinClass.FIRST: Decimal("5.0"),
            CabinClass.CHARTER: Decimal("1.0"),
        }[cabin_class]
        price = _money(Decimal(base) * Decimal(str(round(jitter, 4))) * cabin_multiplier)

        flight_number = f"CX{100 + (abs(hash(seed)) % 900)}"

        return FlightOffer(
            flight_id=flight_id,
            flight_number=flight_number,
            origin=origin,
            destination=destination,
            departure_time=departure_time,
            arrival_time=arrival_time,
            duration_minutes=duration_minutes,
            aircraft=aircraft,
            cabin_class=cabin_class,
            available_seats=available_seats,
            price_per_passenger=price,
            currency="EUR",
            direct=True,
        )

    # ------------------------------------------------------------ aircraft

    def get_aircraft_availability(
        self,
        origin: str | None = None,
        category: str | None = None,
        on_date: date | None = None,
        min_seats: int | None = None,
    ) -> list[Aircraft]:
        results = list(FLEET)
        if origin:
            results = [a for a in results if a.current_location == origin]
        if category:
            results = [a for a in results if a.category == category]
        if min_seats:
            results = [a for a in results if a.seat_capacity >= min_seats]

        out = []
        for a in results:
            if on_date:
                seed = f"avail-{a.id}-{on_date.isoformat()}"
                rng = random.Random(seed)
                available = rng.randint(max(1, a.seat_capacity // 4), a.seat_capacity)
                out.append(replace(a, available_seats=available))
            else:
                out.append(a)
        return out

    # ---------------------------------------------------------------- fare

    def get_fare_quote(
        self,
        flight_id: str,
        adults: int,
        children: int = 0,
        infants: int = 0,
        cabin_class: CabinClass = CabinClass.ECONOMY,
    ) -> FareQuote:
        flight = self.get_flight(flight_id)
        weighted_pax = (
            _PASSENGER_WEIGHT["adult"] * adults
            + _PASSENGER_WEIGHT["child"] * children
            + _PASSENGER_WEIGHT["infant"] * infants
        )
        base_fare = _money(flight.price_per_passenger * weighted_pax)
        taxes = _money(base_fare * _TAX_RATE)
        fees = _BOOKING_FEE
        total = _money(base_fare + taxes + fees)

        quote_id = f"quote_{uuid.uuid4().hex[:20]}"
        quote = FareQuote(
            quote_id=quote_id,
            flight_id=flight_id,
            adults=adults,
            children=children,
            infants=infants,
            cabin_class=cabin_class,
            base_fare=base_fare,
            taxes=taxes,
            fees=fees,
            total_price=total,
            currency=flight.currency,
            expires_at=self._now() + timedelta(minutes=_QUOTE_VALIDITY_MINUTES),
        )
        with self._lock:
            self._quotes[quote_id] = (quote, flight)
        return quote

    # ------------------------------------------------------------ booking

    def create_booking(
        self,
        quote_id: str,
        passengers: list[PassengerInput],
        contact_email: str,
        contact_phone: str,
        idempotency_key: str,
    ) -> ProviderBooking:
        with self._lock:
            existing_ref = self._idempotency_seen.get(idempotency_key)
            if existing_ref:
                return self._bookings[existing_ref]

            entry = self._quotes.get(quote_id)
            if entry is None:
                raise ProviderError("FARE_EXPIRED", f"No such quote: {quote_id}")
            quote, flight = entry
            if self._now() > quote.expires_at:
                raise ProviderError("FARE_EXPIRED", "This fare quote has expired; please re-quote.")

            reference = _make_provider_reference()
            now = self._now()
            booking = ProviderBooking(
                provider_booking_reference=reference,
                status=ProviderBookingStatus.CONFIRMED,
                flight_id=flight.flight_id,
                flight_number=flight.flight_number,
                origin=flight.origin,
                destination=flight.destination,
                departure_time=flight.departure_time,
                arrival_time=flight.arrival_time,
                aircraft_type=flight.aircraft.aircraft_type,
                passengers=list(passengers),
                contact_email=contact_email,
                contact_phone=contact_phone,
                total_price=quote.total_price,
                currency=quote.currency,
                created_at=now,
                updated_at=now,
            )
            self._bookings[reference] = booking
            self._idempotency_seen[idempotency_key] = reference
            return booking

    def get_booking(self, provider_booking_reference: str) -> ProviderBooking:
        booking = self._bookings.get(provider_booking_reference)
        if booking is None:
            raise BookingNotFoundError(provider_booking_reference)
        return booking

    def update_booking(
        self, provider_booking_reference: str, changes: dict, idempotency_key: str
    ) -> ProviderBooking:
        with self._lock:
            existing_ref = self._idempotency_seen.get(idempotency_key)
            if existing_ref:
                return self._bookings[existing_ref]

            booking = self.get_booking(provider_booking_reference)
            if booking.status == ProviderBookingStatus.CANCELLED:
                raise ProviderError("BOOKING_NOT_MODIFIABLE", "Cannot modify a cancelled booking")

            updated = booking
            if "new_flight_id" in changes:
                new_flight = self.get_flight(changes["new_flight_id"])
                pax_count = Decimal(len(booking.passengers)) or Decimal(1)
                new_total = _money(new_flight.price_per_passenger * pax_count * (Decimal("1") + _TAX_RATE) + _BOOKING_FEE)
                updated = replace(
                    updated,
                    flight_id=new_flight.flight_id,
                    flight_number=new_flight.flight_number,
                    origin=new_flight.origin,
                    destination=new_flight.destination,
                    departure_time=new_flight.departure_time,
                    arrival_time=new_flight.arrival_time,
                    aircraft_type=new_flight.aircraft.aircraft_type,
                    total_price=new_total,
                    status=ProviderBookingStatus.MODIFIED,
                )
            if "contact_email" in changes:
                updated = replace(updated, contact_email=changes["contact_email"])
            if "contact_phone" in changes:
                updated = replace(updated, contact_phone=changes["contact_phone"])

            updated = replace(updated, updated_at=self._now())
            self._bookings[provider_booking_reference] = updated
            self._idempotency_seen[idempotency_key] = provider_booking_reference
            return updated

    def cancel_booking(self, provider_booking_reference: str, idempotency_key: str) -> CancellationResult:
        with self._lock:
            existing_ref = self._idempotency_seen.get(idempotency_key)
            booking = self.get_booking(provider_booking_reference)

            if booking.status == ProviderBookingStatus.CANCELLED:
                return CancellationResult(
                    provider_booking_reference=provider_booking_reference,
                    status=ProviderBookingStatus.CANCELLED,
                    refundable_amount=Decimal("0.00"),
                    cancellation_fee=Decimal("0.00"),
                    currency=booking.currency,
                    already_cancelled=True,
                )

            policy = self._compute_cancellation_policy(booking)
            cancelled = replace(booking, status=ProviderBookingStatus.CANCELLED, updated_at=self._now())
            self._bookings[provider_booking_reference] = cancelled
            if existing_ref is None:
                self._idempotency_seen[idempotency_key] = provider_booking_reference

            return CancellationResult(
                provider_booking_reference=provider_booking_reference,
                status=ProviderBookingStatus.CANCELLED,
                refundable_amount=policy.refundable_amount,
                cancellation_fee=policy.cancellation_fee,
                currency=policy.currency,
                already_cancelled=False,
            )

    def get_cancellation_policy(self, provider_booking_reference: str) -> CancellationPolicy:
        booking = self.get_booking(provider_booking_reference)
        return self._compute_cancellation_policy(booking)

    def _compute_cancellation_policy(self, booking: ProviderBooking) -> CancellationPolicy:
        if booking.status == ProviderBookingStatus.CANCELLED:
            return CancellationPolicy(
                provider_booking_reference=booking.provider_booking_reference,
                refundable_amount=Decimal("0.00"),
                cancellation_fee=Decimal("0.00"),
                non_refundable_amount=Decimal("0.00"),
                currency=booking.currency,
                deadline=self._now(),
                already_cancelled=True,
            )
        now = self._now()
        time_to_departure = booking.departure_time - now
        if time_to_departure <= timedelta(hours=24):
            fee_pct = Decimal("0.90")
        elif time_to_departure <= timedelta(hours=48):
            fee_pct = Decimal("0.50")
        elif time_to_departure <= timedelta(days=7):
            fee_pct = Decimal("0.25")
        else:
            fee_pct = Decimal("0.10")

        fee = _money(booking.total_price * fee_pct)
        refundable = _money(booking.total_price - fee)
        return CancellationPolicy(
            provider_booking_reference=booking.provider_booking_reference,
            refundable_amount=refundable,
            cancellation_fee=fee,
            non_refundable_amount=fee,
            currency=booking.currency,
            deadline=now + timedelta(minutes=_QUOTE_VALIDITY_MINUTES),
        )

    # -------------------------------------------------------------- passengers

    def add_passenger(self, provider_booking_reference: str, passenger: PassengerInput) -> ProviderBooking:
        with self._lock:
            booking = self.get_booking(provider_booking_reference)
            if passenger.passenger_id is None:
                passenger.passenger_id = f"pax_{uuid.uuid4().hex[:12]}"
            new_passengers = [*booking.passengers, passenger]
            flight = self.get_flight(booking.flight_id)
            new_total = _money(flight.price_per_passenger * len(new_passengers) * (Decimal("1") + _TAX_RATE) + _BOOKING_FEE)
            updated = replace(booking, passengers=new_passengers, total_price=new_total, updated_at=self._now())
            self._bookings[provider_booking_reference] = updated
            return updated

    def remove_passenger(self, provider_booking_reference: str, passenger_id: str) -> ProviderBooking:
        with self._lock:
            booking = self.get_booking(provider_booking_reference)
            new_passengers = [p for p in booking.passengers if p.passenger_id != passenger_id]
            if len(new_passengers) == len(booking.passengers):
                raise ProviderError("PASSENGER_NOT_FOUND", f"No such passenger on this booking: {passenger_id}")
            if not new_passengers:
                raise ProviderError("PASSENGER_VALIDATION_FAILED", "A booking must have at least one passenger")
            flight = self.get_flight(booking.flight_id)
            new_total = _money(flight.price_per_passenger * len(new_passengers) * (Decimal("1") + _TAX_RATE) + _BOOKING_FEE)
            updated = replace(booking, passengers=new_passengers, total_price=new_total, updated_at=self._now())
            self._bookings[provider_booking_reference] = updated
            return updated

    def get_booking_status(self, provider_booking_reference: str) -> ProviderBookingStatus:
        return self.get_booking(provider_booking_reference).status

    # -------------------------------------------------------------- policies

    def get_baggage_rules(self, cabin_class: CabinClass, aircraft_type: str | None = None) -> BaggageRules:
        table = {
            CabinClass.ECONOMY: (1, 23, 8, Decimal("45.00")),
            CabinClass.PREMIUM_ECONOMY: (2, 23, 10, Decimal("40.00")),
            CabinClass.BUSINESS: (2, 32, 12, Decimal("0.00")),
            CabinClass.FIRST: (3, 32, 12, Decimal("0.00")),
            CabinClass.CHARTER: (4, 23, 10, Decimal("0.00")),
        }
        included, checked_max, cabin_max, extra_fee = table[cabin_class]
        return BaggageRules(
            cabin_class=cabin_class,
            checked_bags_included=included,
            checked_bag_max_kg=checked_max,
            cabin_bag_max_kg=cabin_max,
            extra_bag_fee=extra_fee,
            currency="EUR",
            notes="Pets in an approved carrier may travel in the cabin on most aircraft; "
            "contact us at least 48 hours before departure to arrange this.",
        )

    def get_fare_rules(self, flight_id: str, cabin_class: CabinClass) -> FareRules:
        refundable = cabin_class in (CabinClass.BUSINESS, CabinClass.FIRST)
        return FareRules(
            flight_id=flight_id,
            cabin_class=cabin_class,
            refundable=refundable,
            changeable=True,
            change_fee=Decimal("0.00") if refundable else Decimal("75.00"),
            currency="EUR",
            notes="Changeable on all fares; see get_cancellation_policy for the current refund figures.",
        )


def _great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance. Good enough to make MOCK-mode schedules realistic;
    not a substitute for real flight-planning distance/routing."""
    r_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return r_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _estimate_duration_minutes(origin_ap, dest_ap, rng: random.Random) -> int:
    distance_km = _great_circle_km(origin_ap.latitude, origin_ap.longitude, dest_ap.latitude, dest_ap.longitude)
    ground_ops_overhead_min = 30  # taxi + climb + descent, roughly
    cruise_speed_kmh = 800
    minutes = ground_ops_overhead_min + (distance_km / cruise_speed_kmh) * 60
    return max(35, int(minutes)) + rng.randint(-8, 12)


def _make_flight_id(origin: str, destination: str, departure_date: date, index: int, cabin_class: CabinClass) -> str:
    # Use "_" as the field separator — the ISO date itself contains "-",
    # so splitting on "-" would corrupt it. (Caught by test_core_logic.py.)
    return f"MOCK_{origin}_{destination}_{departure_date.isoformat()}_{index}_{cabin_class.value}"


def _parse_flight_id(flight_id: str) -> tuple[str, str, date, int, CabinClass] | None:
    parts = flight_id.split("_")
    if len(parts) != 6 or parts[0] != "MOCK":
        return None
    try:
        _, origin, destination, date_str, index_str, cabin = parts
        return origin, destination, date.fromisoformat(date_str), int(index_str), CabinClass(cabin)
    except (ValueError, IndexError):
        return None


def _make_provider_reference() -> str:
    return f"PRV{uuid.uuid4().hex[:10].upper()}"
