"""
Booking-verification session state machine (Phase 4 spec §12).

"My booking number is ABC123" does not prove ownership. This models the
controlled verification flow the spec asks for: a short-lived session,
scoped to (call_id, booking_id, purpose), that moves through explicit
states and is what ownership.py's verified-booking-access path checks.

Deliberately dependency-free (stdlib only) — the state machine itself has
no idea what "the right answer" for a given booking is; that's supplied
by the caller (the existing, Phase 1-3
`app.services.verification_service.BookingVerificationService.verify()`
static factor-check — kept as-is and reused here rather than duplicated,
per the instruction not to rewrite working Phase 1-3 logic). This module
only owns the *state machine*: how many attempts have been made, whether
it's expired, and what state a session is in — all of which is real,
testable logic independent of any particular factor-matching rule.

States: UNVERIFIED -> VERIFICATION_PENDING -> VERIFIED | EXPIRED | FAILED
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


DEFAULT_TTL = timedelta(minutes=15)
DEFAULT_MAX_ATTEMPTS = 5


class VerificationSessionError(Exception):
    pass


@dataclass(frozen=True)
class VerificationSessionState:
    """Immutable snapshot — every transition returns a *new* instance
    rather than mutating in place, so a service layer can persist each
    transition as its own row/update without aliasing bugs, and so this
    is trivially testable (assert on the returned value)."""

    id: str
    call_id: Optional[str]
    booking_id: str
    purpose: str  # e.g. "cancel_booking" | "modify_booking" | "view_booking" | "vapi_tool_access"
    status: VerificationStatus
    attempts: int
    max_attempts: int
    created_at: datetime
    expires_at: datetime
    verified_at: Optional[datetime] = None

    @classmethod
    def start(
        cls,
        *,
        session_id: str,
        booking_id: str,
        purpose: str,
        call_id: Optional[str] = None,
        ttl: timedelta = DEFAULT_TTL,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        now: Optional[datetime] = None,
    ) -> "VerificationSessionState":
        now = now or utcnow()
        return cls(
            id=session_id, call_id=call_id, booking_id=booking_id, purpose=purpose,
            status=VerificationStatus.VERIFICATION_PENDING, attempts=0,
            max_attempts=max_attempts, created_at=now, expires_at=now + ttl,
        )

    def _effective_status(self, now: datetime) -> VerificationStatus:
        if self.status in (VerificationStatus.VERIFICATION_PENDING, VerificationStatus.UNVERIFIED):
            if now >= self.expires_at:
                return VerificationStatus.EXPIRED
        return self.status

    def is_usable(self, *, now: Optional[datetime] = None) -> bool:
        """VERIFIED, not expired, not already consumed for a different
        purpose/booking than it was scoped for."""
        now = now or utcnow()
        return self.status == VerificationStatus.VERIFIED and now < self.expires_at

    def submit_factor_result(self, *, matched: bool, now: Optional[datetime] = None) -> "VerificationSessionState":
        now = now or utcnow()
        current = self._effective_status(now)
        if current == VerificationStatus.EXPIRED:
            return replace(self, status=VerificationStatus.EXPIRED)
        if current in (VerificationStatus.VERIFIED, VerificationStatus.FAILED):
            # A terminal, non-expired session doesn't get re-scored — the
            # caller must start a new one. This prevents attempt-counter
            # reuse tricks.
            raise VerificationSessionError(f"session already terminal: {current.value}")

        attempts = self.attempts + 1
        if matched:
            return replace(self, status=VerificationStatus.VERIFIED, attempts=attempts, verified_at=now)
        if attempts >= self.max_attempts:
            return replace(self, status=VerificationStatus.FAILED, attempts=attempts)
        return replace(self, status=VerificationStatus.VERIFICATION_PENDING, attempts=attempts)

    def scoped_to(self, *, booking_id: str, purpose: str) -> bool:
        """§12: 'The verification token must be scoped to call_id,
        booking_id, purpose, expiration.' A VERIFIED session for
        'view_booking' on booking X must not authorize 'cancel_booking' on
        booking X, or anything on booking Y."""
        return self.booking_id == booking_id and self.purpose == purpose

    def current_status(self, *, now: Optional[datetime] = None) -> VerificationStatus:
        return self._effective_status(now or utcnow())
