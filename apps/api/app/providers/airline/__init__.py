"""
Provider factory: this is the ONLY place in the app that should decide
*which* AirlineProvider implementation to use. Every service depends on
the abstract AirlineProvider type (app.providers.airline.base) and gets a
concrete instance from get_airline_provider() — never imports
MockAirlineProvider directly. That's what makes AIRLINE_PROVIDER=amadeus
a config change, not a code change.
"""

from __future__ import annotations

from functools import lru_cache

from app.providers.airline.base import AirlineProvider

# NOTE: get_settings is imported lazily *inside* the function below, not at
# module level. This __init__.py runs whenever ANYTHING imports a submodule
# of app.providers.airline (Python always executes a package's __init__.py
# first) — including app.providers.airline.base and .mock, which are
# deliberately dependency-free so tests/test_core_logic.py can run with
# nothing but the standard library. An eager `from app.core.config import
# get_settings` here would drag pydantic into that import chain and break
# it. (Caught by actually running the tests after adding this factory.)


@lru_cache
def get_airline_provider() -> AirlineProvider:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.airline_provider == "mock":
        from app.providers.airline.mock import MockAirlineProvider

        return MockAirlineProvider()
    if settings.airline_provider == "amadeus":
        from app.providers.airline.amadeus import AmadeusAirlineProvider

        return AmadeusAirlineProvider()
    if settings.airline_provider == "sabre":
        from app.providers.airline.sabre import SabreAirlineProvider

        return SabreAirlineProvider()
    raise ValueError(f"Unknown AIRLINE_PROVIDER: {settings.airline_provider}")
