"""
PaymentProvider — the provider-agnostic contract for payment collection.

Every backend service (PaymentService) talks to *this* interface only. It
never imports MockPaymentProvider or StripePaymentProvider directly
outside of app/providers/payments/__init__.py's factory. That is what
lets STRIPE-only-for-now become a second real provider later without
touching PaymentService — same reasoning as
app/providers/airline/base.py's docstring, mirrored deliberately.

Deliberately dependency-free (stdlib only: abc, dataclasses, datetime,
decimal, enum, typing) so this file — and any provider built against it —
can be imported and unit-tested without FastAPI/SQLAlchemy/`stripe`/a
database being present. app/providers/payments/mock.py follows the same
rule. app/providers/payments/stripe_provider.py does NOT (it genuinely
needs the `stripe` package) — see that module's docstring and
app/providers/payments/__init__.py's lazy-import comment for how the two
constraints coexist.

The primitive this models is a Stripe *Checkout Session* (a Stripe-
hosted, secure payment page), not a raw PaymentIntent embedded in the
Vapi conversation — see app/core/payments/state_machine.py's docstring
for why, and PROJECT_HANDOFF_PHASE_5's Milestone 1 spec §12 ("the Vapi
agent must NOT collect or store raw card information").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class CheckoutSessionStatus(str, Enum):
    OPEN = "open"
    COMPLETE = "complete"
    EXPIRED = "expired"


@dataclass(frozen=True)
class CheckoutSession:
    """What a provider hands back immediately after creating a session —
    everything PaymentService needs to persist a new Payment row."""
    provider_session_id: str
    checkout_url: str
    status: CheckoutSessionStatus
    amount: Decimal
    currency: str
    expires_at: datetime
    payment_intent_id: Optional[str] = None


@dataclass(frozen=True)
class PaymentStatusResult:
    """What get_session_status() returns for a live lookup against the
    provider (used by get_payment_status as a fallback/cross-check —
    the authoritative day-to-day source of truth is still the webhook-
    driven Payment.status in our own database, per §8: "The result must
    come from authoritative backend/provider state," not a live Stripe
    call on every read)."""
    provider_session_id: str
    status: CheckoutSessionStatus
    payment_paid: bool  # Stripe Checkout's own `payment_status == "paid"`
    payment_intent_id: Optional[str]
    amount: Decimal
    currency: str


class RefundStatus(str, Enum):
    """Stripe's own Refund.status vocabulary, verbatim and lowercase
    (per the Refunds API reference: "pending, requires_action, succeeded,
    failed, or canceled") — deliberately NOT uppercased to match
    CheckoutSessionStatus's style, so a value round-tripped from a real
    Stripe response never needs translation. This is a genuinely
    different axis from Payment.status/PAYMENT_SESSION_STATUSES (see
    app/core/payments/state_machine.py): a refund's status describes the
    refund attempt itself, not the Checkout Session, which stays
    SUCCEEDED forever once paid — see app/models/payment.py's refund_*
    columns docstring for why Payment.status is never mutated by a
    refund."""
    PENDING = "pending"
    REQUIRES_ACTION = "requires_action"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class RefundResult:
    """What refund_payment() returns immediately after asking the
    provider to refund a previously-captured payment — mirrors
    CheckoutSession's role for creation. This project has no webhook
    subscription for refund-status-change events (docs/TASK_BOARD.md
    T-3's stated NOT-in-scope) — PaymentService therefore only ever
    trusts this immediate synchronous response. A non-terminal status
    (PENDING/REQUIRES_ACTION) is recorded honestly as such; the booking
    is not marked refunded until a SUCCEEDED result is actually seen."""
    provider_refund_id: str
    status: RefundStatus
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class WebhookEvent:
    """A provider-agnostic shape for the one event type PaymentService
    actually needs to react to. `payment_paid` is None when the event
    type doesn't carry a payment-status signal at all (defensive —
    PaymentService should ignore/no-op unrecognized event types rather
    than error, since Stripe can and does add new event types over
    time)."""
    event_id: str
    event_type: str  # e.g. "checkout.session.completed"
    provider_session_id: Optional[str]
    payment_intent_id: Optional[str]
    payment_paid: Optional[bool]
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None


class PaymentProviderError(Exception):
    """Base class for provider-side failures. Services must catch this
    and translate it into a structured, user-safe error — never a raw
    exception or backend stack trace spoken/shown to a customer. Mirrors
    app/providers/airline/base.py::ProviderError exactly."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


class PaymentSessionCreationError(PaymentProviderError):
    def __init__(self, detail: str = "could not start a payment session"):
        super().__init__("PAYMENT_SESSION_CREATION_FAILED", detail, retryable=True)


class PaymentSessionNotFoundError(PaymentProviderError):
    def __init__(self, provider_session_id: str):
        super().__init__("PAYMENT_SESSION_NOT_FOUND", f"No such payment session: {provider_session_id}", retryable=False)


class PaymentProviderUnavailableError(PaymentProviderError):
    def __init__(self, detail: str = "payment provider temporarily unavailable"):
        super().__init__("PAYMENT_PROVIDER_UNAVAILABLE", detail, retryable=True)


class PaymentRefundError(PaymentProviderError):
    """A refund attempt that the provider explicitly rejected or could
    not complete: already fully refunded, an unknown/mismatched
    PaymentIntent, an amount exceeding what's left on the charge, or a
    terminal FAILED/CANCELED Refund.status. Mirrors
    PaymentSessionCreationError's role for creation — retryable=False
    because every one of those causes is a fact about the payment/
    request, not a transient outage (see PaymentProviderUnavailableError
    for that case instead, used for a generic stripe.StripeError)."""

    def __init__(self, detail: str = "could not process this refund"):
        super().__init__("PAYMENT_REFUND_FAILED", detail, retryable=False)


class WebhookVerificationError(PaymentProviderError):
    """Raised for ANY signature failure — missing header, wrong secret,
    malformed payload, expired timestamp. §9: "Never accept a payment-
    success callback without verifying its Stripe signature" — the
    caller (the webhook route) must treat this as a hard reject, not a
    retryable condition (retryable=False: retrying an invalid signature
    changes nothing)."""

    def __init__(self, detail: str = "invalid webhook signature"):
        super().__init__("WEBHOOK_SIGNATURE_INVALID", detail, retryable=False)


class PaymentProvider(ABC):
    """Provider-agnostic payment-collection interface. Implement this
    once per backend (mock, Stripe, ...) and nothing above this layer
    changes."""

    name: str  # "mock" | "stripe" — stored on Payment.provider_name

    @abstractmethod
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
    ) -> CheckoutSession: ...

    @abstractmethod
    def get_session_status(self, provider_session_id: str) -> PaymentStatusResult: ...

    @abstractmethod
    def verify_and_parse_webhook(self, payload: bytes, signature_header: Optional[str]) -> WebhookEvent: ...

    @abstractmethod
    def refund_payment(
        self,
        *,
        payment_intent_id: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        reason: Optional[str] = None,
    ) -> RefundResult:
        """Refund (fully or partially) a payment that already succeeded.
        Acts on the PaymentIntent, not the Checkout Session (see
        app/models/payment.py::provider_payment_intent_id's docstring —
        this was anticipated since Milestone 1). `amount` is always
        caller-computed and validated BEFORE this is called (never a
        client/LLM-supplied value reaching here unchecked — MASTER_RULES
        §5's principle, applied to refunds too) — see PaymentService.
        refund_payment and CancellationService.cancel for the two
        callers and how each computes it."""
        ...
