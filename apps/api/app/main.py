from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import aircraft, auth, bookings, flights, health, passengers, payments, vapi
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.middleware.csrf import CSRFMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "charter123_api_starting",
        app_env=settings.app_env,
        airline_provider=settings.airline_provider,
        mock_mode=settings.is_mock_mode,
        payment_provider=settings.payment_provider,
    )
    yield
    logger.info("charter123_api_shutting_down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Charter123 AI API",
        version="0.1.0",
        description="Airline voice-agent + booking platform backend. "
        f"Running in {'MOCK' if settings.is_mock_mode else settings.airline_provider.upper()} mode.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Order matters for the request phase: Starlette runs the LAST-added
    # middleware FIRST. Security headers should wrap everything (so they
    # land on error responses too, including CSRF's own 403); CSRF needs
    # to run before a route can mutate state but after CORS has already
    # decided whether this origin is even allowed to be here at all.
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id", f"req_{uuid.uuid4().hex[:16]}")
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(flights.router)
    app.include_router(aircraft.router)
    app.include_router(bookings.router)
    app.include_router(passengers.router)
    app.include_router(payments.router)
    app.include_router(vapi.router)

    return app


app = create_app()
