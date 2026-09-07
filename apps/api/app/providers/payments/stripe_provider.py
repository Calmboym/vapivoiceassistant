"""
StripePaymentProvider — real Stripe Checkout Session integration.

NOT EXECUTED IN THIS SANDBOX: `stripe` is pinned in requirements.txt
(>=11.1,<12.0) but not installed here (no network access to pip install
it — the same constraint documented throughout Phase 5's handoff). This
file has been written and cross-checked against Stripe's current
documentation and stripe-python source (fetched while building this
milestone, not assumed from training data) — specifically:
  - Checkout Session field names (id, url, status, payment_status,
    expires_at as a unix timestamp, amount_total, currency,
    payment_intent) — docs.stripe.com/payments/checkout/how-checkout-works
    and the Session object reference.
  - Webhook event shape ({"id", "type", "data": {"object": {...}}}) and
    the four events this module reacts to (checkout.session.completed,
    .expired, .async_payment_succeeded, .async_payment_failed) — Stripe's
    Checkout events reference. For an async payment method,
    `.completed` fires with payment_status still "unpaid"; the eventual
    outcome arrives later as one of the two async_* events — confirmed
    against Stripe's own guidance on this exact ambiguity, not assumed.
  - Error class names: as of late 2025, `stripe.error.SomeError` (the
    long-documented import path) stopped being importable in current
    stripe-python releases (a confirmed, open upstream issue) — this
    file therefore imports error classes from the TOP-LEVEL `stripe`
    module (`stripe.StripeError`, `stripe.SignatureVerificationError`,
    `stripe.InvalidRequestError`), which Stripe's own current
    error-handling docs use and stripe-python's __init__.py confirms
    are exported there.
  - Resource calls use the long-stable legacy style
    (`stripe.checkout.Session.create/retrieve`, module-level
    `stripe.api_key`) rather than the newer `StripeClient` object —
    search results disagreed on whether that newer client's method
    namespace is `client.checkout.sessions.*` or `client.v1.checkout.
    sessions.*` for this exact pinned version range, and this codebase's
    own rule (§5/§40 in earlier phases: "do not fabricate API shapes")
    means guessing between two live, contradictory sources is worse
    than using the unambiguous, long-documented legacy call style. If a
    later milestone standardizes on StripeClient across this codebase,
    port this one file — nothing above PaymentProvider changes either way.

"Verified against current documentation" is not the same claim as "was
run." Do not represent this file as tested until it has actually been
exercised against a real Stripe test-mode account with the `stripe`
package installed.

Only imported by app/providers/payments/__init__.py's factory, and only
inside the branch that actually selects PAYMENT_PROVIDER=stripe — see
that file's docstring for why the import must stay lazy (this module
does `import stripe` at the top level, which app/providers/payments/base.py
and mock.py deliberately never do, so the dependency-free test suite
never touches this file at all).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import stripe

from app.providers.payments.base import (
    CheckoutSession,
    CheckoutSessionStatus,
    PaymentProvider,
    PaymentProviderUnavailableError,
    PaymentSessionCreationError,
    PaymentSessionNotFoundError,
    PaymentStatusResult,
    WebhookEvent,
    WebhookVerificationError,
)

_STRIPE_TO_INTERNAL_SESSION_STATUS = {
    "open": CheckoutSessionStatus.OPEN,
    "complete": CheckoutSessionStatus.COMPLETE,
    "expired": CheckoutSessionStatus.EXPIRED,
}

# Event types PaymentService reacts to (see that module). Any other
# event type still verifies successfully (a valid signature is a valid
# signature regardless of type) but is returned with event_type set to
# whatever Stripe sent — PaymentService treats an unrecognized type as a
# no-op rather than an error, since Stripe adds new event types over
# time and this endpoint should never break because of one.
RELEVANT_EVENT_TYPES = frozenset({
    "checkout.session.completed",
    "checkout.session.expired",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
})

# Zero-decimal currencies would need `unit_amount` in whole units, not
# cents — this codebase only ever produces EUR/USD amounts today (see
# app/providers/airline/mock.py), so this list exists to fail loudly
# rather than silently mischarge if that ever changes, not because any
# current code path can reach it.
_ZERO_DECIMAL_CURRENCIES = frozenset({
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG",
    "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
})


class StripePaymentProvider(PaymentProvider):
    name = "stripe"

    def __init__(self, *, api_key: str, webhook_secret: str) -> None:
        if not api_key or not webhook_secret:
            raise PaymentProviderUnavailableError(
                "STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET must both be set to use PAYMENT_PROVIDER=stripe"
            )
        # Module-level assignment (the long-stable stripe-python pattern —
        # see module docstring). This is process-global, same tradeoff
        # every single-account Stripe integration accepts; a future
        # multi-account use case would need the newer StripeClient
        # instance-scoped pattern instead of this constructor.
        stripe.api_key = api_key
        self._webhook_secret = webhook_secret

    def create_checkout_session(
        self,
        *,
        reference: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        success_url: str,
        cancel_url: str,
        metadata: dict,
    ) -> CheckoutSession:
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                client_reference_id=reference,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata,
                line_items=[
                    {
                        "quantity": 1,
                        "price_data": {
                            "currency": currency.lower(),
                            "unit_amount": _to_minor_units(amount, currency),
                            "product_data": {"name": f"Charter123 booking {reference}"},
                        },
                    }
                ],
                idempotency_key=idempotency_key,
            )
        except stripe.InvalidRequestError as exc:  # pragma: no cover — needs a real Stripe account to exercise
            raise PaymentSessionCreationError(_safe_stripe_error_message(exc)) from exc
        except stripe.StripeError as exc:  # pragma: no cover
            raise PaymentProviderUnavailableError(_safe_stripe_error_message(exc)) from exc

        return CheckoutSession(
            provider_session_id=session.id,
            checkout_url=session.url,
            status=_STRIPE_TO_INTERNAL_SESSION_STATUS.get(session.status, CheckoutSessionStatus.OPEN),
            amount=amount,
            currency=currency,
            expires_at=datetime.fromtimestamp(session.expires_at, tz=timezone.utc),
            payment_intent_id=(session.payment_intent if isinstance(session.payment_intent, str) else None),
        )

    def get_session_status(self, provider_session_id: str) -> PaymentStatusResult:
        try:
            session = stripe.checkout.Session.retrieve(provider_session_id)
        except stripe.InvalidRequestError as exc:  # pragma: no cover
            raise PaymentSessionNotFoundError(provider_session_id) from exc
        except stripe.StripeError as exc:  # pragma: no cover
            raise PaymentProviderUnavailableError(_safe_stripe_error_message(exc)) from exc

        return PaymentStatusResult(
            provider_session_id=session.id,
            status=_STRIPE_TO_INTERNAL_SESSION_STATUS.get(session.status, CheckoutSessionStatus.OPEN),
            payment_paid=(session.payment_status == "paid"),
            payment_intent_id=(session.payment_intent if isinstance(session.payment_intent, str) else None),
            amount=(Decimal(session.amount_total) / 100) if session.amount_total is not None else Decimal("0"),
            currency=(session.currency or "").upper(),
        )

    def verify_and_parse_webhook(self, payload: bytes, signature_header: Optional[str]) -> WebhookEvent:
        if not signature_header:
            raise WebhookVerificationError("missing Stripe-Signature header")
        try:
            event = stripe.Webhook.construct_event(payload, signature_header, self._webhook_secret)
        except stripe.SignatureVerificationError as exc:  # pragma: no cover
            raise WebhookVerificationError("signature did not match") from exc
        except ValueError as exc:  # pragma: no cover — malformed JSON payload
            raise WebhookVerificationError("malformed payload") from exc

        obj = event["data"]["object"]
        event_type = event["type"]
        payment_paid: Optional[bool] = None
        if event_type in RELEVANT_EVENT_TYPES:
            # payment_status is only ever "paid" | "unpaid" |
            # "no_payment_required" on a Checkout Session — for
            # async_payment_failed the object still reads "unpaid" (it
            # never succeeded), which correctly yields payment_paid=False
            # here; PaymentService distinguishes "still processing" from
            # "definitively failed" using event_type, not this field
            # alone — see that module.
            payment_paid = obj.get("payment_status") == "paid"

        return WebhookEvent(
            event_id=event["id"],
            event_type=event_type,
            provider_session_id=obj.get("id"),
            payment_intent_id=(obj.get("payment_intent") if isinstance(obj.get("payment_intent"), str) else None),
            payment_paid=payment_paid,
            # Deliberately never populated from Stripe's raw error detail
            # (see app/models/payment.py's failure_message docstring) —
            # PaymentService assigns its own short, user-safe failure
            # text based on event_type, not whatever Stripe's internal
            # decline/failure detail happens to say.
            failure_code=None,
            failure_message=None,
        )


def _to_minor_units(amount: Decimal, currency: str) -> int:
    if currency.upper() in _ZERO_DECIMAL_CURRENCIES:
        raise PaymentSessionCreationError(
            f"{currency} is a zero-decimal currency — _to_minor_units needs updating before this can be charged correctly."
        )
    return int((amount * 100).to_integral_value())


def _safe_stripe_error_message(exc: "stripe.StripeError") -> str:
    """Stripe's own exceptions can carry customer-facing-safe text
    (exc.user_message) — prefer that; fall back to a generic message
    rather than str(exc), which can include internal request ids."""
    return getattr(exc, "user_message", None) or "The payment provider could not process this request."
