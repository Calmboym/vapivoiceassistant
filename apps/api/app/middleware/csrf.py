"""
CSRF middleware (§19) — the HTTP-layer enforcement point for
app.core.security.csrf's signed double-submit primitives (dependency-free,
real unit tests in tests/test_security_core.py).

Only applies when BOTH are true:
  (a) the method is state-changing (requires_csrf_check() — POST/PUT/
      PATCH/DELETE, never GET/HEAD/OPTIONS), and
  (b) the request carries the session cookie at all.

No session cookie => not a cookie-authenticated browser request => CSRF
(an attack that rides an *ambient* cookie) doesn't apply. Vapi webhooks
and any future bearer-token server-to-server callers never send this
cookie, so they're naturally exempt — which is correct, not a hole: CSRF
specifically targets cookie-based auth.

/api/v1/auth/login, /register, /request-password-reset, /reset-password
are exempt: a CSRF cookie can only be *validated* against a session that
already exists, and these are exactly the endpoints that create the
first session (or don't need one at all). They're protected by rate
limiting + account lockout instead (§17/§18), not CSRF.

Opens its own short DB session via app.db.session.session_scope() to
resolve the session cookie -> session_id (CSRF tokens are bound to the
session, not just the browser — see csrf.py's module docstring), since
ASGI middleware runs outside FastAPI's Depends() injection.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.security.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, requires_csrf_check, verify_csrf

SESSION_COOKIE_NAME = "c123_session"

_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/request-password-reset",
        "/api/v1/auth/reset-password",
    }
)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if requires_csrf_check(request.method) and request.url.path not in _EXEMPT_PATHS:
            session_token = request.cookies.get(SESSION_COOKIE_NAME)
            if session_token:
                if not self._passes_csrf(request, session_token):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": {
                                "code": "CSRF_FAILED",
                                "message": "This request could not be verified. Please refresh and try again.",
                            }
                        },
                    )
        return await call_next(request)

    @staticmethod
    def _passes_csrf(request: Request, session_token: str) -> bool:
        # Local imports: keep this module importable even before the DB/
        # session-service stack is wired (mirrors the lazy-import
        # pattern already used in app.core.encryption).
        from app.core.security.tokens import hash_token, is_expired
        from app.db.session import session_scope
        from app.models.session import Session as SessionModel

        settings = get_settings()
        cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
        header_value = request.headers.get(CSRF_HEADER_NAME)

        with session_scope() as db:
            session = (
                db.query(SessionModel)
                .filter(SessionModel.session_token_hash == hash_token(session_token))
                .first()
            )
            if session is None or session.revoked_at is not None or is_expired(session.expires_at):
                # An invalid/expired session cookie fails its OWN auth
                # check downstream anyway (get_current_actor treats it as
                # anonymous) — let the request through here and let that
                # layer reject it with the right error code, rather than
                # this middleware returning a confusing CSRF_FAILED for
                # what's really SESSION_EXPIRED.
                return True
            return verify_csrf(
                session_id=str(session.id), secret_key=settings.secret_key,
                cookie_value=cookie_value, header_value=header_value,
            )
