from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.core.exceptions import AuthError
from app.core.security.errors import AuthErrorCode
from app.core.security.rate_limiter import BackoffLockout
from app.core.security.tokens import generate_token, hash_token, verify_token
from app.core.security.verification import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TTL,
    VerificationSessionError,
    VerificationSessionState,
    VerificationStatus,
)
from app.models.booking import Booking
from app.models.verification import VerificationSession
from app.repositories.verification_repository import VerificationRepository


class BookingVerificationService:
    """Knowing a PNR is never enough on its own (§13). Any sensitive action —
    cancellation, passenger info, payment info, itinerary changes — must
    additionally match the contact email/phone on file, or a passenger's
    last name. This is intentionally simple (exact, case-insensitive
    match); production should also rate-limit verification attempts per
    PNR via Redis (see app/db/redis_client.py) to slow down guessing."""

    @staticmethod
    def verify(
        booking: Booking,
        *,
        email_or_phone: str | None = None,
        last_name: str | None = None,
    ) -> bool:
        if email_or_phone:
            candidate = email_or_phone.strip().lower()
            if candidate == (booking.contact_email or "").strip().lower():
                return True
            if candidate == (booking.contact_phone or "").strip().lower():
                return True
        if last_name:
            candidate_name = last_name.strip().lower()
            for passenger in booking.passengers:
                if passenger.last_name.strip().lower() == candidate_name:
                    return True
        return False


class VerificationSessionService:
    """The stateful wrapper around BookingVerificationService.verify()
    (§12): turns a *successful* factor check into a short-lived, scoped
    token via app.core.security.verification's pure, tested state
    machine, and turns a *failed* attempt into a tracked, rate-limitable
    one instead of allowing unlimited re-guessing against the same PNR.

    This is the fix for the real gap found while auditing Phase 1-3's
    cancel/modify routes: they previously trusted nothing but a
    client-supplied `customer_confirmed: bool` for a sensitive mutation.
    After this phase, an anonymous/voice caller's cancel/modify request
    must present a token from a *completed* `submit()` call here — see
    app/api/routes/bookings.py and app.core.security.ownership.
    authorize_booking_access()'s `verification_purpose` parameter, which
    is exactly what `check()` below feeds.

    The DB row (app.models.verification.VerificationSession) stores only
    `token_hash` — never the raw token — same rule as sessions and
    password-reset tokens (see app.core.security.tokens).
    """

    def __init__(self, db: DBSession, *, rate_limiter: Optional[BackoffLockout] = None):
        self.db = db
        self.repo = VerificationRepository(db)
        self.rate_limiter = rate_limiter

    @staticmethod
    def _to_state(record: VerificationSession) -> VerificationSessionState:
        return VerificationSessionState(
            id=str(record.id),
            call_id=record.call_id,
            booking_id=record.booking_id,
            purpose=record.purpose,
            status=VerificationStatus(record.status),
            attempts=record.attempts,
            max_attempts=DEFAULT_MAX_ATTEMPTS,
            created_at=record.created_at,
            expires_at=record.expires_at,
            verified_at=record.verified_at,
        )

    def start(self, *, booking_id: str, purpose: str, call_id: Optional[str] = None) -> str:
        """Returns the RAW token — hand it back to the caller (e.g. as
        part of the tool result a Vapi assistant relays, or a web
        response) and nowhere else. Only its hash is persisted."""
        raw_token = generate_token()
        now = datetime.now(timezone.utc)
        record = VerificationSession(
            call_id=call_id,
            booking_id=booking_id,
            purpose=purpose,
            token_hash=hash_token(raw_token),
            status=VerificationStatus.VERIFICATION_PENDING.value,
            attempts=0,
            expires_at=now + DEFAULT_TTL,
        )
        self.repo.add(record)
        return raw_token

    def submit(
        self,
        *,
        raw_token: str,
        booking: Booking,
        email_or_phone: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> VerificationSession:
        record = self.repo.get_by_token_hash(hash_token(raw_token))
        if record is None or not verify_token(raw_token, record.token_hash):
            raise AuthError(AuthErrorCode.BOOKING_VERIFICATION_FAILED, "Verification session not found.")

        lock_key = f"verify:{record.booking_id}"
        if self.rate_limiter is not None:
            lock_state = self.rate_limiter.is_locked(lock_key)
            if not lock_state.allowed:
                raise AuthError(
                    AuthErrorCode.RATE_LIMITED, "Too many verification attempts. Please try again shortly."
                )

        matched = BookingVerificationService.verify(booking, email_or_phone=email_or_phone, last_name=last_name)

        state = self._to_state(record)
        try:
            updated = state.submit_factor_result(matched=matched)
        except VerificationSessionError:
            # Already terminal (VERIFIED/FAILED) and re-submitted — don't
            # silently re-score it (that's exactly the attempt-counter
            # reuse trick §12/§32 warn about). Surface as a clean 403,
            # not a 500.
            raise AuthError(
                AuthErrorCode.VERIFICATION_EXPIRED,
                "This verification session can no longer be used — please start a new one.",
            )

        record.status = updated.status.value
        record.attempts = updated.attempts
        record.verified_at = updated.verified_at

        if self.rate_limiter is not None:
            if matched:
                self.rate_limiter.record_success(lock_key)
            else:
                self.rate_limiter.record_failure(lock_key)

        return record

    def check(self, *, raw_token: str, booking_id: str, purpose: str) -> bool:
        """The gate app.core.security.ownership.authorize_booking_access()
        is ultimately fed by (via the route layer): does this raw token
        correspond to a VERIFIED, unexpired session scoped to exactly
        this booking_id + purpose? Never raises — a bad/missing/expired
        token is just `False`, same as "not verified"."""
        record = self.repo.get_by_token_hash(hash_token(raw_token))
        if record is None or not verify_token(raw_token, record.token_hash):
            return False
        state = self._to_state(record)
        return state.is_usable() and state.scoped_to(booking_id=booking_id, purpose=purpose)
