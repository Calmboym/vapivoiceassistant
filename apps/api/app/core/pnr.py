"""
PNR generation for OUR booking record (app.models.booking.Booking.pnr) — this
is distinct from a provider_booking_reference, which the AirlineProvider
issues for its own (possibly external, real-world) system. Per §9: never
expose internal DB IDs to customers; the PNR is the only identifier a
customer should ever hear or see.
"""

from __future__ import annotations

import secrets
from typing import Callable

# Excludes 0/O and 1/I to avoid ambiguity when read aloud or over the phone.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_LENGTH = 6
_MAX_ATTEMPTS = 25


def generate_pnr() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))


def generate_unique_pnr(exists: Callable[[str], bool]) -> str:
    """`exists(pnr)` should check the database for a collision. Raises
    RuntimeError if no unique PNR was found in _MAX_ATTEMPTS tries (should
    be statistically near-impossible at 32^6 ≈ 1.07 billion combinations)."""
    for _ in range(_MAX_ATTEMPTS):
        candidate = generate_pnr()
        if not exists(candidate):
            return candidate
    raise RuntimeError("Could not generate a unique PNR — check the PNR keyspace/collision rate")
