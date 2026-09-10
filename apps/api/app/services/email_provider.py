"""
Email delivery abstraction (§6: "Email verification architecture should
be prepared. Do not send real emails if no provider is configured. Use
MockEmailProvider in development.").

T-5 (docs/TASK_BOARD.md, Phase 8): extends the original two auth-only
methods (send_password_reset/send_email_verification, Phase 1-3) with
two new ones — send_booking_confirmation/send_payment_link — and adds a
real provider, ResendEmailProvider, alongside MockEmailProvider. The
Protocol's EXISTING two methods are unchanged (same names, same
signatures) — this is an addition, not a redesign, per WBS-4.1's "don't
change the interface shape without reason." AuthService/auth.py's
existing import and call site (get_email_provider().send_password_reset)
keep working exactly as before.

ResendEmailProvider talks to Resend's REST API directly over `httpx`
(already a project dependency — see requirements.txt — used elsewhere
for e.g. scripts/setup_vapi.py's VapiClient) rather than adding the
`resend` PyPI package as a new dependency. `httpx` is imported LAZILY
inside the method that needs it, not at module level — same reason
app/providers/payments/stripe_provider.py lazy-imports `stripe`, and
app/providers/payments/__init__.py's factory comment explains at length:
selecting EMAIL_PROVIDER=mock (the default) must never require httpx to
be importable, only MockEmailProvider needs to import cleanly for the
dependency-free test suite.

Resend API contract below (POST https://api.resend.com/emails) was
fetched from Resend's own current API reference during this session
(https://resend.com/docs/api-reference/emails/send-email), not assumed
from training data — cross-checked the same way StripePaymentProvider
was in Phase 6/T-3:
  - Auth: `Authorization: Bearer <RESEND_API_KEY>`.
  - Body: {"from", "to", "subject", "html", "text"} — "to" accepts a
    single string or array; this codebase always sends to one recipient.
  - Idempotency: an `Idempotency-Key` HTTP header, deduplicated by
    Resend for 24h — used here the same way StripePaymentProvider
    forwards idempotency_key to Stripe (T-3's docstring explains that
    pattern in full).
  - Success response: {"id": "<email id>"}.
  - Error response: {"statusCode": <int>, "message": "<str>", "name":
    "<error_code>"} — confirmed against a real observed error body
    (resend-node issue #286) and Resend's own Rust/Elixir SDK source,
    which both deserialize exactly these three fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.core.notifications.content import NotificationContent


class EmailProvider(Protocol):
    def send_password_reset(self, *, to_email: str, reset_url: str) -> None: ...
    def send_email_verification(self, *, to_email: str, verify_url: str) -> None: ...

    def send_booking_confirmation(
        self, *, to_email: str, pnr: str, content: NotificationContent, idempotency_key: str
    ) -> None: ...

    def send_payment_link(
        self, *, to_email: str, pnr: str, content: NotificationContent, idempotency_key: str
    ) -> None: ...


class EmailDeliveryError(Exception):
    """Raised by a real provider (ResendEmailProvider) when a send
    genuinely fails — never raised by MockEmailProvider, which cannot
    fail. Callers (app/services/notification_service.py) MUST catch this
    — see that module's docstring for why a failed email must never
    block or roll back the booking/payment mutation that already
    succeeded. Mirrors PaymentProviderError's role/shape (code + message
    + retryable), not a subclass of it — email and payments are
    unrelated provider families, same reasoning AirlineProvider and
    PaymentProvider each get their own independent error hierarchy
    rather than sharing one."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


@dataclass
class SentEmail:
    to_email: str
    kind: str
    context: dict = field(default_factory=dict)


class MockEmailProvider:
    """Records what would have been sent instead of sending it. `sent`
    is a plain list so a test (or a dev poking at the API by hand) can
    read the reset/verification link straight off it instead of it
    disappearing into a real inbox."""

    name = "mock"

    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    def send_password_reset(self, *, to_email: str, reset_url: str) -> None:
        self.sent.append(SentEmail(to_email=to_email, kind="password_reset", context={"reset_url": reset_url}))

    def send_email_verification(self, *, to_email: str, verify_url: str) -> None:
        self.sent.append(
            SentEmail(to_email=to_email, kind="email_verification", context={"verify_url": verify_url})
        )

    def send_booking_confirmation(
        self, *, to_email: str, pnr: str, content: NotificationContent, idempotency_key: str
    ) -> None:
        self.sent.append(
            SentEmail(
                to_email=to_email, kind="booking_confirmation",
                context={"pnr": pnr, "subject": content.subject, "idempotency_key": idempotency_key},
            )
        )

    def send_payment_link(
        self, *, to_email: str, pnr: str, content: NotificationContent, idempotency_key: str
    ) -> None:
        self.sent.append(
            SentEmail(
                to_email=to_email, kind="payment_link",
                context={"pnr": pnr, "subject": content.subject, "idempotency_key": idempotency_key},
            )
        )


class ResendEmailProvider:
    """Real Resend-backed implementation. WRITTEN, CROSS-CHECKED AGAINST
    LIVE RESEND DOCS — NEVER EXECUTED (no network access in any sandbox
    this project has used to date; see docs/handoffs/ for the
    project-wide pattern). `httpx` is imported lazily inside _post(), not
    at module/class level — see module docstring."""

    name = "resend"

    def __init__(self, *, api_key: str, from_address: str, timeout_seconds: float = 10.0):
        self.api_key = api_key
        self.from_address = from_address
        self.timeout_seconds = timeout_seconds

    def _post(self, *, subject: str, to_email: str, text_body: str, html_body: str, idempotency_key: str) -> None:
        import httpx  # lazy — see module docstring

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }
        payload = {
            "from": self.from_address,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }
        try:
            response = httpx.post(
                "https://api.resend.com/emails", json=payload, headers=headers, timeout=self.timeout_seconds
            )
        except httpx.HTTPError as exc:
            raise EmailDeliveryError("EMAIL_PROVIDER_UNAVAILABLE", str(exc), retryable=True) from exc

        if response.status_code >= 400:
            try:
                body = response.json()
                message = body.get("message", response.text)
                name = body.get("name", "unknown_error")
            except Exception:
                message = response.text
                name = "unknown_error"
            # 429/5xx are Resend-side and plausibly transient; other 4xx
            # (bad address, malformed payload, etc.) is a fact about this
            # specific request, not worth retrying verbatim — same
            # retryable split PaymentProviderUnavailableError vs
            # PaymentSessionCreationError already draws in
            # app/providers/payments/base.py.
            retryable = response.status_code == 429 or response.status_code >= 500
            raise EmailDeliveryError(f"RESEND_{name.upper()}", message, retryable=retryable)

    def send_password_reset(self, *, to_email: str, reset_url: str) -> None:
        self._post(
            subject="Reset your Charter123 password",
            to_email=to_email,
            text_body=f"Reset your password: {reset_url}\nIf you didn't request this, you can ignore this email.",
            html_body=(
                f'<p>Reset your password: <a href="{reset_url}">{reset_url}</a></p>'
                f"<p>If you didn't request this, you can ignore this email.</p>"
            ),
            idempotency_key=f"password_reset/{to_email}/{reset_url}",
        )

    def send_email_verification(self, *, to_email: str, verify_url: str) -> None:
        self._post(
            subject="Verify your Charter123 email",
            to_email=to_email,
            text_body=f"Verify your email: {verify_url}",
            html_body=f'<p>Verify your email: <a href="{verify_url}">{verify_url}</a></p>',
            idempotency_key=f"email_verification/{to_email}/{verify_url}",
        )

    def send_booking_confirmation(
        self, *, to_email: str, pnr: str, content: NotificationContent, idempotency_key: str
    ) -> None:
        self._post(
            subject=content.subject, to_email=to_email, text_body=content.text_body,
            html_body=content.html_body, idempotency_key=idempotency_key,
        )

    def send_payment_link(
        self, *, to_email: str, pnr: str, content: NotificationContent, idempotency_key: str
    ) -> None:
        self._post(
            subject=content.subject, to_email=to_email, text_body=content.text_body,
            html_body=content.html_body, idempotency_key=idempotency_key,
        )


def get_email_provider() -> EmailProvider:
    # Mirrors app/providers/payments/__init__.py's factory pattern
    # exactly: branch on settings, lazy-import get_settings() itself so
    # a "mock" selection never drags pydantic into MockEmailProvider's
    # import chain either.
    from app.core.config import get_settings

    settings = get_settings()
    if settings.email_provider == "resend":
        return ResendEmailProvider(
            api_key=settings.resend_api_key or "", from_address=settings.email_from_address or ""
        )
    return MockEmailProvider()
