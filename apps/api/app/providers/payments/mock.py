"""
MockPaymentProvider — deterministic, in-memory, no network calls.

Used whenever PAYMENT_PROVIDER=mock (the default — see app/providers/
payments/__init__.py) and by every dependency-free test in
tests/test_payments_core.py. Deliberately dependency-free itself (stdlib
only), same rule as app/providers/airline/mock.py.

Determinism, concretely:
  - The same idempotency_key ALWAYS produces the same session (mirrors
    what passing `idempotency_key=` to a real Stripe API call does —
    see StripePaymentProvider) — no randomness, so a retried
    create_payment_session call is provably a no-op at the provider
    layer, not just "probably fine because nothing failed in testing."
  - provider_session_id is derived from the idempotency_key via SHA-256,
    not uuid4 — same input always produces the same session id, which
    tests can assert on directly.
  - `simulate_completion()` / `simulate_expiry()` / `build_webhook_event()`
    are the ONLY way a mock session's state ever changes — there is no
    background clock, no real network call, nothing "happens" on its
    own. A test drives the exact scenario it wants and nothing else.
  - `refund_payment()` (T-3) is looked up by `payment_intent_id`, not
    `provider_session_id` — matching what a real refund actually acts on
    (see PaymentProvider.refund_payment's docstring). The same
    idempotency_key always returns the same RefundResult; refunding more
    than what's left on the payment (tracked per-session, across
    however many partial refund_payment calls) raises PaymentRefundError
    rather than silently over-refunding.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from app.providers.payments.base import (
    CheckoutSession,
    CheckoutSessionStatus,
    PaymentProvider,
    PaymentRefundError,
    PaymentSessionNotFoundError,
    PaymentStatusResult,
    RefundResult,
    RefundStatus,
    WebhookEvent,
    WebhookVerificationError,
)

# The only signature value this provider ever accepts. Real Stripe uses
# HMAC-SHA256 over the raw payload with a timestamp (see
# StripePaymentProvider) — this mock deliberately does NOT reimplement
# that, because the property worth testing here is "PaymentService
# rejects an unverified webhook," not "this mock can compute HMAC-SHA256"
# (that's stripe.Webhook.construct_event's job, exercised only where
# `stripe` is actually installed).
MOCK_VALID_SIGNATURE = "mock_valid_signature"


@dataclass
class _MockSession:
    provider_session_id: str
    amount: Decimal
    currency: str
    status: CheckoutSessionStatus = CheckoutSessionStatus.OPEN
    payment_paid: bool = False
    payment_intent_id: Optional[str] = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24))
    refunded_amount: Decimal = field(default_factory=lambda: Decimal("0"))


class MockPaymentProvider(PaymentProvider):
    name = "mock"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_idempotency_key: dict[str, str] = {}  # idempotency_key -> provider_session_id
        self._sessions: dict[str, _MockSession] = {}   # provider_session_id -> session
        self._refunds: dict[str, RefundResult] = {}    # idempotency_key -> RefundResult (dedup, mirrors sessions)

    def _session_id_for(self, idempotency_key: str) -> str:
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"mock_cs_{digest[:24]}"

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
        del reference, success_url, cancel_url, metadata  # not needed by the mock
        with self._lock:
            existing_id = self._by_idempotency_key.get(idempotency_key)
            if existing_id is not None:
                # Idempotent replay — same key, same session, no new
                # state created. See module docstring.
                s = self._sessions[existing_id]
                return CheckoutSession(
                    provider_session_id=s.provider_session_id,
                    checkout_url=f"https://mock-checkout.charter123.test/{s.provider_session_id}",
                    status=s.status, amount=s.amount, currency=s.currency,
                    expires_at=s.expires_at, payment_intent_id=s.payment_intent_id,
                )
            session_id = self._session_id_for(idempotency_key)
            session = _MockSession(provider_session_id=session_id, amount=amount, currency=currency)
            self._sessions[session_id] = session
            self._by_idempotency_key[idempotency_key] = session_id
            return CheckoutSession(
                provider_session_id=session_id,
                checkout_url=f"https://mock-checkout.charter123.test/{session_id}",
                status=session.status, amount=amount, currency=currency,
                expires_at=session.expires_at, payment_intent_id=None,
            )

    def get_session_status(self, provider_session_id: str) -> PaymentStatusResult:
        with self._lock:
            s = self._sessions.get(provider_session_id)
            if s is None:
                raise PaymentSessionNotFoundError(provider_session_id)
            return PaymentStatusResult(
                provider_session_id=s.provider_session_id, status=s.status,
                payment_paid=s.payment_paid, payment_intent_id=s.payment_intent_id,
                amount=s.amount, currency=s.currency,
            )

    def refund_payment(
        self,
        *,
        payment_intent_id: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        reason: Optional[str] = None,
    ) -> RefundResult:
        del reason  # not needed by the mock — real Stripe just records it on the Refund object
        with self._lock:
            existing = self._refunds.get(idempotency_key)
            if existing is not None:
                # Idempotent replay — same key, same refund, no double
                # refund. Same reasoning as create_checkout_session.
                return existing

            session = next(
                (s for s in self._sessions.values() if s.payment_intent_id == payment_intent_id), None
            )
            if session is None:
                raise PaymentRefundError(f"No such payment intent to refund: {payment_intent_id}")
            if not session.payment_paid:
                raise PaymentRefundError(f"Payment intent {payment_intent_id} was never captured — nothing to refund.")
            if session.refunded_amount + amount > session.amount:
                remaining = session.amount - session.refunded_amount
                raise PaymentRefundError(
                    f"Refund amount {amount} {currency} exceeds the {remaining} {currency} remaining on this payment."
                )

            digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
            refund_id = f"mock_re_{digest[:24]}"
            result = RefundResult(
                provider_refund_id=refund_id, status=RefundStatus.SUCCEEDED, amount=amount, currency=currency
            )
            session.refunded_amount += amount
            self._refunds[idempotency_key] = result
            return result

    def verify_and_parse_webhook(self, payload: bytes, signature_header: Optional[str]) -> WebhookEvent:
        if signature_header != MOCK_VALID_SIGNATURE:
            raise WebhookVerificationError("mock provider rejected this signature")
        try:
            event = json.loads(payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload)
        except (TypeError, ValueError) as exc:
            raise WebhookVerificationError("malformed webhook payload") from exc
        obj = (event.get("data") or {}).get("object") or {}
        payment_status = obj.get("payment_status")
        return WebhookEvent(
            event_id=event.get("id", ""),
            event_type=event.get("type", ""),
            provider_session_id=obj.get("id"),
            payment_intent_id=obj.get("payment_intent"),
            payment_paid=(payment_status == "paid") if payment_status is not None else None,
            failure_code=obj.get("failure_code"),
            failure_message=obj.get("failure_message"),
        )

    # --- test-only helpers, not part of the PaymentProvider contract ---

    def simulate_completion(self, provider_session_id: str, *, paid: bool = True, payment_intent_id: str = "pi_mock_1") -> None:
        with self._lock:
            s = self._sessions[provider_session_id]
            s.status = CheckoutSessionStatus.COMPLETE
            s.payment_paid = paid
            s.payment_intent_id = payment_intent_id

    def simulate_expiry(self, provider_session_id: str) -> None:
        with self._lock:
            s = self._sessions[provider_session_id]
            s.status = CheckoutSessionStatus.EXPIRED

    def build_webhook_event(self, *, event_id: str, event_type: str, provider_session_id: str) -> bytes:
        """Builds the exact JSON payload verify_and_parse_webhook() (or a
        real Stripe SDK) expects, from a session this mock already knows
        about — for tests to hand to PaymentService.handle_webhook_event()
        alongside MOCK_VALID_SIGNATURE."""
        s = self._sessions[provider_session_id]
        payload = {
            "id": event_id,
            "type": event_type,
            "data": {
                "object": {
                    "id": s.provider_session_id,
                    "payment_status": "paid" if s.payment_paid else "unpaid",
                    "payment_intent": s.payment_intent_id,
                }
            },
        }
        return json.dumps(payload).encode("utf-8")
