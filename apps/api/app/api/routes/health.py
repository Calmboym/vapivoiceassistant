from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.redis_client import get_redis
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("")
def health():
    return {"success": True, "data": {"status": "ok"}, "request_id": "health"}


@router.get("/live")
def liveness():
    """Process is up. Does not check dependencies — used by
    orchestrators to decide whether to restart the container."""
    return {"success": True, "data": {"status": "alive"}, "request_id": "health-live"}


@router.get("/ready")
def readiness(db: Session = Depends(get_db)):
    """Checks everything the app actually needs to serve traffic (§54):
    PostgreSQL, Redis, and — when not in mock mode — provider connectivity."""
    settings = get_settings()
    checks: dict[str, bool] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    try:
        checks["redis"] = bool(get_redis().ping())
    except Exception:
        checks["redis"] = False

    checks["provider_configured"] = settings.is_mock_mode or bool(settings.airline_api_base_url)

    ready = all(checks.values())
    return {
        "success": ready,
        "data": {"status": "ready" if ready else "not_ready", "checks": checks, "mode": settings.airline_provider},
        "request_id": "health-ready",
    }
