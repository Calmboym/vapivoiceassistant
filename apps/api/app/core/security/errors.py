"""
Auth/authz error codes (Phase 4 spec §27).

Deliberately dependency-free (stdlib only) so it can be imported and
unit-tested without FastAPI/SQLAlchemy present — see
tests/test_security_core.py.

These are *codes*, not exception classes — app/core/exceptions.py already
has a small set of AppError subclasses (UnauthorizedError, ForbiddenError,
VerificationFailedError, ConflictError, ...) that map to HTTP statuses.
The FastAPI layer raises those with one of the codes below as the `code`
argument, e.g. `raise UnauthorizedError(AuthErrorCode.SESSION_EXPIRED, "...")`.
Keeping the codes as a plain enum here (rather than one exception subclass
per code) means this file has zero framework dependency and the full list
is testable on its own — see AuthErrorCodeTests.
"""

from __future__ import annotations

from enum import Enum


class AuthErrorCode(str, Enum):
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    ACCOUNT_PENDING_VERIFICATION = "ACCOUNT_PENDING_VERIFICATION"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_REVOKED = "SESSION_REVOKED"
    FORBIDDEN = "FORBIDDEN"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    BOOKING_VERIFICATION_REQUIRED = "BOOKING_VERIFICATION_REQUIRED"
    BOOKING_VERIFICATION_FAILED = "BOOKING_VERIFICATION_FAILED"
    VERIFICATION_EXPIRED = "VERIFICATION_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    CSRF_FAILED = "CSRF_FAILED"
    WEAK_PASSWORD = "WEAK_PASSWORD"
    EMAIL_ALREADY_REGISTERED = "EMAIL_ALREADY_REGISTERED"
    INVALID_TOKEN = "INVALID_TOKEN"

    # Every code maps to exactly one HTTP status. This is the single
    # source of truth the FastAPI exception handler consults — see
    # app/core/exceptions.py's extended _AUTH_ERROR_HTTP_STATUS map.


HTTP_STATUS_FOR_CODE: dict[AuthErrorCode, int] = {
    AuthErrorCode.AUTHENTICATION_REQUIRED: 401,
    AuthErrorCode.INVALID_CREDENTIALS: 401,
    AuthErrorCode.ACCOUNT_SUSPENDED: 403,
    AuthErrorCode.ACCOUNT_DISABLED: 403,
    AuthErrorCode.ACCOUNT_PENDING_VERIFICATION: 403,
    AuthErrorCode.SESSION_EXPIRED: 401,
    AuthErrorCode.SESSION_REVOKED: 401,
    AuthErrorCode.FORBIDDEN: 403,
    AuthErrorCode.PERMISSION_DENIED: 403,
    AuthErrorCode.BOOKING_VERIFICATION_REQUIRED: 403,
    AuthErrorCode.BOOKING_VERIFICATION_FAILED: 403,
    AuthErrorCode.VERIFICATION_EXPIRED: 403,
    AuthErrorCode.RATE_LIMITED: 429,
    AuthErrorCode.CSRF_FAILED: 403,
    AuthErrorCode.WEAK_PASSWORD: 422,
    AuthErrorCode.EMAIL_ALREADY_REGISTERED: 409,
    AuthErrorCode.INVALID_TOKEN: 400,
}

# Section 33/28: login and registration responses must never reveal
# whether a given email exists. Both "no such user" and "user exists but
# wrong password" collapse to this single generic message/code pair.
GENERIC_LOGIN_FAILURE_MESSAGE = "Incorrect email or password."
GENERIC_PASSWORD_RESET_MESSAGE = (
    "If an account exists for that email, a password reset link has been sent."
)
