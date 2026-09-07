"""
Seeds `airports` and `aircraft` from the same reference data
MockAirlineProvider uses (app/providers/airline/reference_data.py), so the
DB tables used for validation/admin display and the mock provider's own
in-memory world stay consistent.

Run with:  python -m app.db.seed
(from apps/api/, after `alembic upgrade head`)

Idempotent: re-running it updates existing rows rather than duplicating them.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.security.rbac import ROLE_PERMISSIONS
from app.db.session import session_scope
from app.models.aircraft import Aircraft
from app.models.airport import Airport
from app.providers.airline.reference_data import AIRPORTS, FLEET
from app.repositories.rbac_repository import RbacRepository

logger = get_logger(__name__)


def seed_airports(db) -> int:
    count = 0
    for iata, ap in AIRPORTS.items():
        existing = db.get(Airport, iata)
        if existing:
            existing.icao, existing.name, existing.city = ap.icao, ap.name, ap.city
            existing.country, existing.timezone = ap.country, ap.timezone
            existing.latitude, existing.longitude = ap.latitude, ap.longitude
        else:
            db.add(
                Airport(
                    iata=ap.iata, icao=ap.icao, name=ap.name, city=ap.city, country=ap.country,
                    timezone=ap.timezone, latitude=ap.latitude, longitude=ap.longitude, active=True,
                )
            )
        count += 1
    return count


def seed_aircraft(db) -> int:
    count = 0
    for craft in FLEET:
        existing = db.query(Aircraft).filter_by(registration=craft.registration).one_or_none()
        if existing:
            existing.manufacturer, existing.model = craft.manufacturer, craft.model
            existing.aircraft_type, existing.category = craft.aircraft_type, craft.category
            existing.seat_capacity, existing.range_km = craft.seat_capacity, craft.range_km
            existing.baggage_capacity_kg = craft.baggage_capacity_kg
            existing.cabin_configuration = craft.cabin_configuration
            existing.amenities, existing.status = list(craft.amenities), craft.status
            existing.current_location = craft.current_location
        else:
            db.add(
                Aircraft(
                    registration=craft.registration, manufacturer=craft.manufacturer, model=craft.model,
                    aircraft_type=craft.aircraft_type, category=craft.category, seat_capacity=craft.seat_capacity,
                    range_km=craft.range_km, baggage_capacity_kg=craft.baggage_capacity_kg,
                    cabin_configuration=craft.cabin_configuration, amenities=list(craft.amenities),
                    status=craft.status, current_location=craft.current_location,
                )
            )
        count += 1
    return count


def seed_rbac(db) -> int:
    """Loads app.core.security.rbac.ROLE_PERMISSIONS — the pure,
    dependency-free, unit-tested matrix — into the roles/permissions/
    role_permissions tables (§8/§30). Idempotent: re-running replaces
    each role's permission set with the current matrix rather than
    accumulating stale grants, so upgrading the app and re-seeding
    actually revokes anything removed from the matrix, not just adds."""
    repo = RbacRepository(db)
    count = 0
    for role_name, permissions in ROLE_PERMISSIONS.items():
        role = repo.upsert_role(role_name)
        repo.set_role_permissions(role, permissions)
        count += 1
    return count


def run() -> None:
    with session_scope() as db:
        n_airports = seed_airports(db)
        n_aircraft = seed_aircraft(db)
        n_roles = seed_rbac(db)
    logger.info("seed_complete", airports=n_airports, aircraft=n_aircraft, roles=n_roles)
    print(f"Seeded {n_airports} airports, {n_aircraft} aircraft, and {n_roles} roles (with their permissions).")


if __name__ == "__main__":
    run()
