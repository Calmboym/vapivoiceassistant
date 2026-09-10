"""
Pure, dependency-free content builders for customer-facing notifications
(Phase 8 — booking confirmation, payment-link delivery; T-5,
docs/TASK_BOARD.md).

Deliberately stdlib-only (dataclasses, datetime, decimal, typing) —
mirrors app/core/payments/state_machine.py and
app/providers/payments/base.py's own "no FastAPI/SQLAlchemy/network
import here" discipline. The point is specifically so the actually-risky
part of this feature — what text goes out to a real customer — gets
real, executed, dependency-free test coverage in this sandbox, the same
way MockPaymentProvider's refund math did in T-3. See
tests/test_notifications_core.py.

Callers (app/services/notification_service.py) convert SQLAlchemy
Booking/Payment/BookingPassenger ORM objects into the plain dataclasses
below BEFORE calling into this module — this module never imports
app.models.* or SQLAlchemy, on purpose, so it stays testable here.

Content rules enforced here, all traceable to MASTER_RULES.md:
  - NEVER a passport number, passport country, or passport expiry field
    anywhere in these dataclasses or the text they produce (§5:
    "Passport numbers are... never returned in full"). This is enforced
    STRUCTURALLY, not by a runtime check: PassengerSummary below has no
    passport-shaped field at all, so there is nothing for a content
    builder to accidentally leak — the same "structural enforcement over
    runtime checks" principle MASTER_RULES.md applies to authorization,
    applied here to a privacy boundary instead.
  - NEVER a fabricated cancellation fee, refund amount, or baggage
    figure (§1: "never invent... policy. If the backend doesn't have it,
    say so honestly"). `cancellation_deadline` and `baggage` are both
    Optional — when the caller doesn't have real data for either (as of
    T-5, Booking.cancellation_deadline is a pre-existing, never-populated
    nullable column — see the T-5 handoff), the builders below emit an
    honest, generic sentence instead of a guessed number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class PassengerSummary:
    """Deliberately narrow — first/last name and passenger type only.
    No passport_number, passport_country, passport_expiry, date_of_birth,
    frequent_flyer_number, or any other field appears here on purpose;
    see module docstring."""

    first_name: str
    last_name: str
    passenger_type: str  # "adult" | "child" | "infant"


@dataclass(frozen=True)
class BaggageAllowance:
    """Populated only when AirlineProvider.get_baggage_rules() actually
    returned something for this booking's aircraft type — see
    NotificationService.send_booking_confirmation's docstring for the
    documented CabinClass.ECONOMY default assumption this is built from
    (Booking does not persist which cabin class was booked). Never
    fabricated when that lookup fails or is unavailable: the caller
    passes baggage=None for the whole field in that case, not a guessed
    BaggageAllowance."""

    checked_bags_included: int
    checked_bag_max_kg: int
    cabin_bag_max_kg: int


@dataclass(frozen=True)
class BookingConfirmationData:
    pnr: str
    origin: str
    destination: str
    flight_number: str
    aircraft_type: str
    departure_time: datetime
    arrival_time: datetime
    currency: str
    total_price: Decimal
    payment_status: str
    passengers: tuple[PassengerSummary, ...]
    cancellation_deadline: Optional[datetime] = None
    baggage: Optional[BaggageAllowance] = None


@dataclass(frozen=True)
class PaymentLinkData:
    pnr: str
    amount: Decimal
    currency: str
    checkout_url: str
    expires_at: datetime


@dataclass(frozen=True)
class NotificationContent:
    subject: str
    text_body: str
    html_body: str


def _fmt_dt(dt: datetime) -> str:
    # Spelled out manually (not a locale-dependent %A/%B strftime) so
    # this is deterministic across environments/tests.
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt.tzinfo is not None else dt.strftime("%Y-%m-%d %H:%M")


def _fmt_money(amount: Decimal, currency: str) -> str:
    return f"{amount:.2f} {currency}"


def build_booking_confirmation_email(data: BookingConfirmationData) -> NotificationContent:
    subject = f"Your Charter123 booking {data.pnr} is confirmed"

    passenger_text = "\n".join(f"  - {p.first_name} {p.last_name} ({p.passenger_type})" for p in data.passengers)
    passenger_html = "".join(
        f"<li>{p.first_name} {p.last_name} ({p.passenger_type})</li>" for p in data.passengers
    )

    if data.cancellation_deadline is not None:
        cancellation_text = f"Free cancellation until {_fmt_dt(data.cancellation_deadline)}."
    else:
        cancellation_text = (
            "Cancellation fees depend on how close to departure you cancel — look up your booking "
            "any time to see the exact refund amount before you confirm a cancellation."
        )

    if data.baggage is not None:
        baggage_text = (
            f"{data.baggage.checked_bags_included} checked bag(s) included, up to "
            f"{data.baggage.checked_bag_max_kg}kg each; cabin bag up to {data.baggage.cabin_bag_max_kg}kg."
        )
    else:
        baggage_text = "Baggage allowance depends on your fare — contact us or check your booking for details."

    text_body = (
        f"Booking confirmation — {data.pnr}\n\n"
        f"Flight {data.flight_number} ({data.aircraft_type})\n"
        f"{data.origin} -> {data.destination}\n"
        f"Departs: {_fmt_dt(data.departure_time)}\n"
        f"Arrives: {_fmt_dt(data.arrival_time)}\n\n"
        f"Passengers:\n{passenger_text}\n\n"
        f"Total: {_fmt_money(data.total_price, data.currency)}\n"
        f"Payment status: {data.payment_status.lower()}\n\n"
        f"Baggage: {baggage_text}\n\n"
        f"Cancellation: {cancellation_text}\n\n"
        f"Confirmation number: {data.pnr}\n"
    )

    html_body = (
        f"<h2>Booking confirmation — {data.pnr}</h2>"
        f"<p>Flight {data.flight_number} ({data.aircraft_type})<br>"
        f"{data.origin} &rarr; {data.destination}<br>"
        f"Departs: {_fmt_dt(data.departure_time)}<br>"
        f"Arrives: {_fmt_dt(data.arrival_time)}</p>"
        f"<p>Passengers:</p><ul>{passenger_html}</ul>"
        f"<p>Total: {_fmt_money(data.total_price, data.currency)}<br>"
        f"Payment status: {data.payment_status.lower()}</p>"
        f"<p>Baggage: {baggage_text}</p>"
        f"<p>Cancellation: {cancellation_text}</p>"
    )

    return NotificationContent(subject=subject, text_body=text_body, html_body=html_body)


def build_payment_link_email(data: PaymentLinkData) -> NotificationContent:
    subject = f"Complete your payment for booking {data.pnr}"
    text_body = (
        f"A secure payment link is ready for your booking {data.pnr}.\n\n"
        f"Amount due: {_fmt_money(data.amount, data.currency)}\n"
        f"Pay here: {data.checkout_url}\n\n"
        f"This link expires {_fmt_dt(data.expires_at)}. It takes you to Stripe's own secure payment page — "
        f"we never ask for your card details directly.\n"
    )
    html_body = (
        f"<p>A secure payment link is ready for your booking <strong>{data.pnr}</strong>.</p>"
        f"<p>Amount due: {_fmt_money(data.amount, data.currency)}</p>"
        f'<p><a href="{data.checkout_url}">Pay now</a></p>'
        f"<p>This link expires {_fmt_dt(data.expires_at)}. It takes you to Stripe's own secure payment page — "
        f"we never ask for your card details directly.</p>"
    )
    return NotificationContent(subject=subject, text_body=text_body, html_body=html_body)


def build_payment_link_sms(data: PaymentLinkData) -> str:
    # Not padded/truncated to a specific segment count on purpose —
    # Twilio segments long bodies automatically (see
    # app/services/sms_provider.py) — but kept lean so a typical PNR/URL
    # combination doesn't needlessly spill into a second segment.
    return (
        f"Charter123: pay {_fmt_money(data.amount, data.currency)} for booking {data.pnr} here: "
        f"{data.checkout_url} (expires {_fmt_dt(data.expires_at)})"
    )
