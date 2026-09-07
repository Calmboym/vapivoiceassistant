"""
Payment session state machine (Phase 6 Milestone 1).

These states describe a *Stripe Checkout Session* — the primitive
create_payment_session actually creates (per PROJECT_HANDOFF_PHASE_5's
Milestone 1 spec §12: the Vapi channel must never collect card data
itself, only hand back a link to Stripe's own hosted, secure payment
page). They are deliberately NOT the six states an earlier draft spec
suggested verbatim (PENDING/REQUIRES_ACTION/PROCESSING/SUCCEEDED/FAILED/
CANCELED/EXPIRED) — REQUIRES_ACTION is a raw-PaymentIntent concept
(3DS/SCA authentication step) that Stripe's own Checkout Session webhooks
never surface as a distinct session-level state; Checkout handles that
internally before ever firing `checkout.session.completed`. Six states
were "appropriate to the actual lifecycle" (per that spec's own
instruction not to blindly copy); this is five, derived from Stripe's
documented Checkout Session events:

  PENDING     Session created (Stripe status "open"), awaiting the
              customer to complete or abandon Stripe's hosted page.
  PROCESSING  `checkout.session.completed` fired, but Checkout's own
              `payment_status` was NOT yet "paid" at that moment — an
              async payment method (e.g. a bank debit) is still
              settling. Resolves later via async_payment_succeeded/
              async_payment_failed. (The common case — a card — jumps
              PENDING -> SUCCEEDED directly, since payment_status is
              already "paid" by the time `.completed` fires.)
  SUCCEEDED   Payment captured. Terminal.
  FAILED      An async payment method ultimately failed
              (`checkout.session.async_payment_failed`). Terminal.
  EXPIRED     The session's 24h (default) window elapsed with the
              customer never completing it (`checkout.session.expired`).
              Terminal — nothing was ever charged, so this is NOT the
              same as FAILED for the purpose of retry messaging.
  CANCELED    Charter123-side administrative supersession — e.g. a new
              create_payment_session call is made for a booking that
              already has a PENDING session; the stale one is marked
              CANCELED rather than left dangling. Terminal. Nothing in
              Milestone 1 exposes a *tool* that causes this — it's an
              internal bookkeeping state, not an LLM-callable action.

Retry behavior: none of the terminal states auto-retry. A FAILED/
EXPIRED/CANCELED session simply stops mattering; calling
create_payment_session again for the same booking starts a brand new
session (a new Payment row, a new Stripe Checkout Session, a new
idempotency_key) — it does not attempt to resurrect the old one, because
Stripe Checkout Sessions are not resumable past `open`.
"""

from __future__ import annotations

PAYMENT_SESSION_STATUSES: tuple[str, ...] = (
    "PENDING", "PROCESSING", "SUCCEEDED", "FAILED", "EXPIRED", "CANCELED",
)

TERMINAL_PAYMENT_SESSION_STATUSES: frozenset[str] = frozenset(
    {"SUCCEEDED", "FAILED", "EXPIRED", "CANCELED"}
)

# What a Payment row is allowed to transition *to* from its current
# status. Not a graph of what triggers each transition (that's
# PaymentService's job, driven by real Stripe webhook event types) —
# just which destinations are ever legal, so an invalid transition is a
# loud ValueError instead of a silently-accepted data-integrity bug.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"PROCESSING", "SUCCEEDED", "FAILED", "EXPIRED", "CANCELED"}),
    "PROCESSING": frozenset({"SUCCEEDED", "FAILED"}),
    "SUCCEEDED": frozenset(),
    "FAILED": frozenset(),
    "EXPIRED": frozenset(),
    "CANCELED": frozenset(),
}


def can_transition(current_status: str, new_status: str) -> bool:
    if new_status not in PAYMENT_SESSION_STATUSES:
        return False
    return new_status in _ALLOWED_TRANSITIONS.get(current_status, frozenset())


def is_terminal(status: str) -> bool:
    return status in TERMINAL_PAYMENT_SESSION_STATUSES


# A Payment's session status, translated into the (pre-existing, Phase
# 1-3) Booking.payment_status vocabulary — UNPAID/PENDING/PAID/REFUNDED/
# FAILED (app/models/booking.py::PAYMENT_STATUSES). Deliberately reuses
# those five values rather than inventing new ones on Booking (per the
# Milestone 1 spec §10: "Do not invent a new booking state without
# examining the existing booking lifecycle") — REFUNDED is intentionally
# absent from this map because nothing in Milestone 1 ever produces it;
# that value stays CancellationService's alone (see its module for the
# known-limitation note this creates once payments can reach PAID).
#
# EXPIRED/CANCELED both fall back to booking "UNPAID": nothing was ever
# charged in either case, so the booking is exactly as payable as it was
# before create_payment_session was called — this is a reset, not a
# failure state, which is why it's UNPAID rather than FAILED.
BOOKING_PAYMENT_STATUS_FOR_SESSION: dict[str, str] = {
    "PENDING": "PENDING",
    "PROCESSING": "PENDING",
    "SUCCEEDED": "PAID",
    "FAILED": "FAILED",
    "EXPIRED": "UNPAID",
    "CANCELED": "UNPAID",
}

# Booking.payment_status values create_payment_session refuses to start
# a new session from — a real, unresolved-by-Milestone-1 payment is
# already in flight (PENDING) or the booking is already paid (PAID) or
# already refunded (REFUNDED, staff-only territory). UNPAID and FAILED
# are the only two states a *new* attempt may start from.
BOOKING_PAYMENT_STATUSES_BLOCKING_NEW_SESSION: frozenset[str] = frozenset({"PENDING", "PAID", "REFUNDED"})


# The four Stripe Checkout Session webhook event types this system acts
# on (see app/providers/payments/stripe_provider.py's module docstring
# for how these were confirmed against Stripe's current documentation).
# Any other event type PaymentService receives (should its Stripe
# endpoint ever be subscribed to more than these) is accepted — a valid
# signature is a valid signature — but produces no status transition.
RELEVANT_WEBHOOK_EVENT_TYPES: frozenset[str] = frozenset({
    "checkout.session.completed",
    "checkout.session.expired",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
})


def new_status_for_webhook_event(event_type: str, payment_paid) -> "str | None":
    """Pure mapping from a provider-agnostic webhook event to the
    PAYMENT_SESSION_STATUSES value it implies. Both StripePaymentProvider
    (real events) and MockPaymentProvider (synthetic ones built by
    build_webhook_event(), for tests) funnel through the exact same
    decision here — this is the one place that decision is made, so it
    can be tested without a database and without `stripe` installed.

    `payment_paid` only disambiguates `checkout.session.completed`
    (paid immediately, e.g. a card, vs. still-settling, e.g. an async
    debit) — for the other three event types the type alone determines
    the outcome regardless of what payment_paid says (see
    stripe_provider.py's comment on why async_payment_failed's embedded
    object still reads payment_status="unpaid", not some distinct
    "failed" value — Stripe's Checkout Session object has no such value).

    Returns None for an event type this system doesn't act on.
    """
    if event_type == "checkout.session.completed":
        return "SUCCEEDED" if payment_paid else "PROCESSING"
    if event_type == "checkout.session.async_payment_succeeded":
        return "SUCCEEDED"
    if event_type == "checkout.session.async_payment_failed":
        return "FAILED"
    if event_type == "checkout.session.expired":
        return "EXPIRED"
    return None
