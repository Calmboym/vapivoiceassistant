"""
Structured error codes (§37) and the exception -> HTTP response mapping.
Nothing in here ever leaks a stack trace or raw exception text to a client
(§36: "Never return stack traces to clients.").
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.core.security.errors import HTTP_STATUS_FOR_CODE, AuthErrorCode
from app.providers.airline.base import ProviderError
from app.providers.payments.base import PaymentProviderError

logger = get_logger(__name__)


class AppError(Exception):
    """Base application error. Route handlers should raise a subclass of
    this (or ProviderError, handled separately) rather than returning
    ad-hoc error dicts, so every error goes through the same envelope."""

    http_status: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class NotFoundError(AppError):
    http_status = status.HTTP_404_NOT_FOUND


class ValidationFailedError(AppError):
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


class ConflictError(AppError):
    http_status = status.HTTP_409_CONFLICT


class VerificationFailedError(AppError):
    http_status = status.HTTP_403_FORBIDDEN


class UnauthorizedError(AppError):
    http_status = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AppError):
    http_status = status.HTTP_403_FORBIDDEN


class RateLimitedError(AppError):
    http_status = status.HTTP_429_TOO_MANY_REQUESTS


class AuthError(AppError):
    """Phase 4's error codes (app.core.security.errors.AuthErrorCode)
    don't map 1:1 onto the existing per-status classes above — e.g.
    ACCOUNT_SUSPENDED and FORBIDDEN are both 403 but RATE_LIMITED is 429
    and INVALID_TOKEN is 400. Rather than making every Phase 4 call site
    remember which of NotFoundError/ForbiddenError/UnauthorizedError/...
    happens to match a given code (easy to get wrong, and something DID
    briefly go wrong this way during development — see
    docs/PRODUCTION_CHECKLIST.md and PROJECT_HANDOFF_PHASE_4.md §5),
    AuthError derives its http_status automatically from
    HTTP_STATUS_FOR_CODE, so `raise AuthError(AuthErrorCode.RATE_LIMITED, "...")`
    always produces exactly the status that table specifies."""

    def __init__(self, code: "AuthErrorCode | str", message: str):
        resolved = code if isinstance(code, AuthErrorCode) else AuthErrorCode(code)
        self.http_status = HTTP_STATUS_FOR_CODE[resolved]
        super().__init__(resolved.value, message)


_PROVIDER_ERROR_HTTP_STATUS = {
    "FLIGHT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "BOOKING_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "UNKNOWN_AIRPORT": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "INVALID_ROUTE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "FARE_EXPIRED": status.HTTP_409_CONFLICT,
    "BOOKING_NOT_MODIFIABLE": status.HTTP_409_CONFLICT,
    "PASSENGER_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "PASSENGER_VALIDATION_FAILED": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "PROVIDER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
}

# Phase 6 Milestone 1 — mirrors _PROVIDER_ERROR_HTTP_STATUS exactly, one
# table per provider family (airline vs. payments) rather than merging
# them, since the two ProviderError base classes are intentionally
# distinct types (see app/providers/payments/base.py's docstring).
_PAYMENT_PROVIDER_ERROR_HTTP_STATUS = {
    "PAYMENT_SESSION_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "PAYMENT_SESSION_CREATION_FAILED": status.HTTP_502_BAD_GATEWAY,
    "PAYMENT_PROVIDER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
    "WEBHOOK_SIGNATURE_INVALID": status.HTTP_400_BAD_REQUEST,
}


def _envelope_error(request_id: str, code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}, "request_id": request_id}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.info("app_error", code=exc.code, path=request.url.path, request_id=request_id)
        return JSONResponse(
            status_code=exc.http_status,
            content=_envelope_error(request_id, exc.code, exc.message),
        )

    @app.exception_handler(ProviderError)
    async def handle_provider_error(request: Request, exc: ProviderError):
        request_id = getattr(request.state, "request_id", "unknown")
        http_status = _PROVIDER_ERROR_HTTP_STATUS.get(exc.code, status.HTTP_502_BAD_GATEWAY)
        logger.warning(
            "provider_error", code=exc.code, retryable=exc.retryable, path=request.url.path, request_id=request_id
        )
        # Customer/agent-safe message only — never the raw provider detail
        # unless it was already written to be spoken (ProviderError.message
        # is authored for that purpose in this codebase; a real GDS
        # adapter's exceptions should be translated before reaching here).
        return JSONResponse(
            status_code=http_status,
            content=_envelope_error(request_id, exc.code, exc.message),
        )

    @app.exception_handler(PaymentProviderError)
    async def handle_payment_provider_error(request: Request, exc: PaymentProviderError):
        request_id = getattr(request.state, "request_id", "unknown")
        http_status = _PAYMENT_PROVIDER_ERROR_HTTP_STATUS.get(exc.code, status.HTTP_502_BAD_GATEWAY)
        logger.warning(
            "payment_provider_error", code=exc.code, retryable=exc.retryable,
            path=request.url.path, request_id=request_id,
        )
        # Same trust level as ProviderError.message above — every
        # PaymentProviderError subclass is constructed with an
        # already-user-safe message (see app/providers/payments/base.py
        # and stripe_provider.py's _safe_stripe_error_message), never a
        # raw Stripe exception string.
        return JSONResponse(
            status_code=http_status,
            content=_envelope_error(request_id, exc.code, exc.message),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error("unhandled_exception", path=request.url.path, request_id=request_id, exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope_error(request_id, "INTERNAL_ERROR", "Something went wrong on our end."),
        )
