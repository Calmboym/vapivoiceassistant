"""
Security response headers (§21). Applied to every response. These don't
touch CORS (handled by Starlette's CORSMiddleware from
settings.cors_origin_list — see app/main.py) and don't restrict a
same-origin JSON API response or the Vapi webhook/Next.js frontend's
normal calls in any way a legitimate caller would notice.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        settings = get_settings()

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

        # A JSON API renders no HTML itself, so a strict default-src
        # 'none' CSP is safe everywhere except FastAPI's own /docs and
        # /redoc pages, which need their known Swagger/ReDoc CDN assets.
        if request.url.path in ("/docs", "/redoc"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data: https://fastapi.tiangolo.com; "
                "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'",
            )
        else:
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'")

        if settings.app_env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload"
            )
        return response
