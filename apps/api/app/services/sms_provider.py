"""
SMS delivery abstraction — new in T-5 (docs/TASK_BOARD.md, Phase 8,
WBS-4.2: "this is new; no interface exists yet, so design one mirroring
the email provider's shape"). Deliberately mirrors
app/services/email_provider.py's structure (Protocol + Mock + real
provider + factory, all in one file) rather than inventing a different
convention for a sibling notification channel.

Only one method exists so far — send_payment_link — because that's the
one T-5 scope item (WBS-4.4) that actually needs SMS: a phone caller
mid-call has no path to a computer, so the payment link goes to their
phone, not just their inbox (see docs/PAYMENTS.md §8's documented gap,
now closed). Booking confirmation (WBS-4.3) stays email-only — spec §44's
content list (full itinerary, every passenger, baggage note,
cancellation terms) does not fit an SMS segment and wasn't asked for on
this channel; see the T-5 handoff for the full reasoning.

TwilioSmsProvider talks to Twilio's REST API directly over `httpx`
(already a project dependency), the same lazy-import-for-a-real-provider
pattern app/services/email_provider.py's ResendEmailProvider and
app/providers/payments/stripe_provider.py both use, and for the same
reason: EMAIL_PROVIDER=mock / SMS_PROVIDER=mock (both defaults) must
never require httpx to be importable.

Twilio API contract below (POST
https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages.json)
was fetched from Twilio's own current API reference during this session
(https://www.twilio.com/docs/messaging/api/message-resource), not
assumed from training data:
  - Auth: HTTP Basic (username=Account SID, password=Auth Token).
  - Body: `application/x-www-form-urlencoded` — To, From, Body.
  - Idempotency: the `I-Twilio-Idempotency-Token` header (Twilio's
    general retry-distinguishing mechanism, documented at
    twilio.com/docs/usage/webhooks/webhooks-connection-overrides and
    confirmed applicable to the Messages resource specifically).
  - Success response (201): JSON body including "sid", "status",
    "error_code" (null on success).
  - Error response: {"code": <int>, "message": "<str>", "more_info":
    "<url>", "status": <http_status>} — confirmed against a real
    observed Twilio error body (missing 'To' parameter, error 21604) and
    the Twilio Go SDK's own ErrorResponse struct, which deserializes
    exactly these four fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class SmsProvider(Protocol):
    def send_payment_link(self, *, to_phone: str, pnr: str, text_body: str, idempotency_key: str) -> None: ...


class SmsDeliveryError(Exception):
    """Raised by a real provider (TwilioSmsProvider) when a send
    genuinely fails — never raised by MockSmsProvider. Callers
    (app/services/notification_service.py) MUST catch this — see that
    module's docstring for why a failed SMS must never block or roll
    back the payment-session creation that already succeeded. Mirrors
    EmailDeliveryError's shape (code + message + retryable) for the same
    reason that file gives; not a shared base class, since email and SMS
    are still unrelated provider families."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


@dataclass
class SentSms:
    to_phone: str
    kind: str
    context: dict = field(default_factory=dict)


class MockSmsProvider:
    """Records what would have been sent instead of sending it — same
    role/shape as MockEmailProvider."""

    name = "mock"

    def __init__(self) -> None:
        self.sent: list[SentSms] = []

    def send_payment_link(self, *, to_phone: str, pnr: str, text_body: str, idempotency_key: str) -> None:
        self.sent.append(
            SentSms(
                to_phone=to_phone, kind="payment_link",
                context={"pnr": pnr, "text_body": text_body, "idempotency_key": idempotency_key},
            )
        )


class TwilioSmsProvider:
    """Real Twilio-backed implementation. WRITTEN, CROSS-CHECKED AGAINST
    LIVE TWILIO DOCS — NEVER EXECUTED (no network access in any sandbox
    this project has used to date). `httpx` is imported lazily inside
    send_payment_link(), not at module/class level — see module
    docstring."""

    name = "twilio"

    def __init__(self, *, account_sid: str, auth_token: str, from_number: str, timeout_seconds: float = 10.0):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.timeout_seconds = timeout_seconds

    def send_payment_link(self, *, to_phone: str, pnr: str, text_body: str, idempotency_key: str) -> None:
        import httpx  # lazy — see module docstring

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        headers = {"I-Twilio-Idempotency-Token": idempotency_key}
        data = {"To": to_phone, "From": self.from_number, "Body": text_body}
        try:
            response = httpx.post(
                url, data=data, headers=headers, auth=(self.account_sid, self.auth_token),
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise SmsDeliveryError("SMS_PROVIDER_UNAVAILABLE", str(exc), retryable=True) from exc

        if response.status_code >= 400:
            try:
                body = response.json()
                message = body.get("message", response.text)
                code = body.get("code", "unknown_error")
            except Exception:
                message = response.text
                code = "unknown_error"
            # 429/5xx are Twilio-side and plausibly transient; other 4xx
            # (invalid 'To' number, unverified trial number, etc.) is a
            # fact about this specific request — same retryable split
            # ResendEmailProvider draws in app/services/email_provider.py.
            retryable = response.status_code == 429 or response.status_code >= 500
            raise SmsDeliveryError(f"TWILIO_{code}", message, retryable=retryable)


def get_sms_provider() -> SmsProvider:
    # Mirrors get_email_provider()/get_payment_provider()'s factory
    # pattern exactly — see those modules for the lazy-import reasoning.
    from app.core.config import get_settings

    settings = get_settings()
    if settings.sms_provider == "twilio":
        return TwilioSmsProvider(
            account_sid=settings.twilio_account_sid or "",
            auth_token=settings.twilio_auth_token or "",
            from_number=settings.twilio_phone_number or "",
        )
    return MockSmsProvider()
