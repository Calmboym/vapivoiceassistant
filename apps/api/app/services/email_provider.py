"""
Email delivery abstraction (§6: "Email verification architecture should
be prepared. Do not send real emails if no provider is configured. Use
MockEmailProvider in development.").

Only MockEmailProvider exists. A real provider (Resend — RESEND_API_KEY
is already in app/core/config.py from Phase 1-3) is Phase 6's job
("email/SMS notifications", explicitly out of scope for this phase per
docs/PRODUCTION_CHECKLIST.md). This interface exists now so AuthService
never sends a raw email itself, mirroring the AirlineProvider pattern in
app/providers/airline/base.py — Phase 6 has exactly one seam to plug a
real implementation into, and that implementation should fail loudly if
misconfigured rather than silently no-op, same principle as the airline
provider adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class EmailProvider(Protocol):
    def send_password_reset(self, *, to_email: str, reset_url: str) -> None: ...
    def send_email_verification(self, *, to_email: str, verify_url: str) -> None: ...


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

    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    def send_password_reset(self, *, to_email: str, reset_url: str) -> None:
        self.sent.append(SentEmail(to_email=to_email, kind="password_reset", context={"reset_url": reset_url}))

    def send_email_verification(self, *, to_email: str, verify_url: str) -> None:
        self.sent.append(
            SentEmail(to_email=to_email, kind="email_verification", context={"verify_url": verify_url})
        )


def get_email_provider() -> EmailProvider:
    # Always Mock for now. Deliberately NOT branching on
    # settings.resend_api_key here — wiring that up is Phase 6's job,
    # and doing it half-here would mean it ships untested. See module
    # docstring.
    return MockEmailProvider()
