"""
Static seed data for MOCK mode: airports, fleet, and airport-group aliases.

This is intentionally hand-authored and deterministic — it is the mock
provider's "world state," not a substitute for the real `airports` /
`aircraft` DB tables in app/models (those exist independently and are what
the rest of the application, e.g. disambiguation and the admin UI, reads).
"""

from __future__ import annotations

from app.providers.airline.base import Aircraft, Airport

AIRPORTS: dict[str, Airport] = {
    a.iata: a
    for a in [
        Airport("FRA", "EDDF", "Frankfurt Airport", "Frankfurt", "Germany", "Europe/Berlin", 50.0379, 8.5622),
        Airport("BER", "EDDB", "Berlin Brandenburg Airport", "Berlin", "Germany", "Europe/Berlin", 52.3667, 13.5033),
        Airport("MUC", "EDDM", "Munich Airport", "Munich", "Germany", "Europe/Berlin", 48.3538, 11.7861),
        Airport("HAM", "EDDH", "Hamburg Airport", "Hamburg", "Germany", "Europe/Berlin", 53.6304, 9.9882),
        Airport("CDG", "LFPG", "Charles de Gaulle Airport", "Paris", "France", "Europe/Paris", 49.0097, 2.5479),
        Airport("LHR", "EGLL", "Heathrow Airport", "London", "United Kingdom", "Europe/London", 51.4700, -0.4543),
        Airport("LGW", "EGKK", "Gatwick Airport", "London", "United Kingdom", "Europe/London", 51.1537, -0.1821),
        Airport("STN", "EGSS", "Stansted Airport", "London", "United Kingdom", "Europe/London", 51.8860, 0.2389),
        Airport("LTN", "EGGW", "Luton Airport", "London", "United Kingdom", "Europe/London", 51.8747, -0.3683),
        Airport("DXB", "OMDB", "Dubai International Airport", "Dubai", "United Arab Emirates", "Asia/Dubai", 25.2532, 55.3657),
        Airport("DOH", "OTHH", "Hamad International Airport", "Doha", "Qatar", "Asia/Qatar", 25.2609, 51.6138),
        Airport("JFK", "KJFK", "John F. Kennedy International Airport", "New York", "United States", "America/New_York", 40.6413, -73.7781),
        Airport("LAX", "KLAX", "Los Angeles International Airport", "Los Angeles", "United States", "America/Los_Angeles", 33.9416, -118.4085),
        Airport("IST", "LTFM", "Istanbul Airport", "Istanbul", "Turkey", "Europe/Istanbul", 41.2753, 28.7519),
        Airport("AMS", "EHAM", "Amsterdam Airport Schiphol", "Amsterdam", "Netherlands", "Europe/Amsterdam", 52.3105, 4.7683),
        Airport("MAD", "LEMD", "Adolfo Suárez Madrid–Barajas Airport", "Madrid", "Spain", "Europe/Madrid", 40.4983, -3.5676),
        Airport("FCO", "LIRF", "Leonardo da Vinci–Fiumicino Airport", "Rome", "Italy", "Europe/Rome", 41.8003, 12.2389),
        Airport("NCE", "LFMN", "Nice Côte d'Azur Airport", "Nice", "France", "Europe/Paris", 43.6584, 7.2159),
    ]
}

# "Any London airport" style disambiguation groups, per MASTER BUILD PROMPT §6.
AIRPORT_GROUPS: dict[str, tuple[str, ...]] = {
    "LONDON": ("LHR", "LGW", "STN", "LTN"),
}

CITY_TO_AIRPORTS: dict[str, tuple[str, ...]] = {
    "london": AIRPORT_GROUPS["LONDON"],
    "frankfurt": ("FRA",),
    "berlin": ("BER",),
    "munich": ("MUC",),
    "hamburg": ("HAM",),
    "paris": ("CDG",),
    "dubai": ("DXB",),
    "doha": ("DOH",),
    "new york": ("JFK",),
    "los angeles": ("LAX",),
    "istanbul": ("IST",),
    "amsterdam": ("AMS",),
    "madrid": ("MAD",),
    "rome": ("FCO",),
    "nice": ("NCE",),
}

FLEET: list[Aircraft] = [
    Aircraft(
        id="ac-a320-01", registration="D-CHTA", manufacturer="Airbus", model="A320",
        aircraft_type="A320", category="commercial", seat_capacity=180, available_seats=180,
        range_km=6100, baggage_capacity_kg=2000, cabin_configuration="3-3 economy",
        amenities=("wifi", "power outlets"), status="available", current_location="FRA",
        next_available_at=None,
    ),
    Aircraft(
        id="ac-a321-01", registration="D-CHTB", manufacturer="Airbus", model="A321",
        aircraft_type="A321", category="commercial", seat_capacity=220, available_seats=220,
        range_km=5900, baggage_capacity_kg=2200, cabin_configuration="3-3 economy + business",
        amenities=("wifi", "power outlets", "business class"), status="available", current_location="FRA",
        next_available_at=None,
    ),
    Aircraft(
        id="ac-b737-01", registration="D-CHTC", manufacturer="Boeing", model="737-800",
        aircraft_type="737", category="commercial", seat_capacity=189, available_seats=189,
        range_km=5400, baggage_capacity_kg=2100, cabin_configuration="3-3 economy",
        amenities=("wifi",), status="available", current_location="MUC",
        next_available_at=None,
    ),
    Aircraft(
        id="ac-e190-01", registration="D-CHTD", manufacturer="Embraer", model="E190",
        aircraft_type="E190", category="commercial", seat_capacity=100, available_seats=100,
        range_km=4500, baggage_capacity_kg=1200, cabin_configuration="2-2 economy",
        amenities=(), status="available", current_location="HAM",
        next_available_at=None,
    ),
    Aircraft(
        id="ac-g650-01", registration="D-CHTE", manufacturer="Gulfstream", model="G650",
        aircraft_type="G650", category="charter", seat_capacity=18, available_seats=18,
        range_km=13890, baggage_capacity_kg=1500, cabin_configuration="charter",
        amenities=("wifi", "full galley", "flat-bed seats"), status="available", current_location="FRA",
        next_available_at=None,
    ),
    Aircraft(
        id="ac-ch350-01", registration="D-CHTF", manufacturer="Bombardier", model="Challenger 350",
        aircraft_type="CL350", category="charter", seat_capacity=10, available_seats=10,
        range_km=5900, baggage_capacity_kg=800, cabin_configuration="charter",
        amenities=("wifi", "galley"), status="available", current_location="BER",
        next_available_at=None,
    ),
    Aircraft(
        id="ac-clat-01", registration="D-CHTG", manufacturer="Cessna", model="Citation Latitude",
        aircraft_type="CLAT", category="charter", seat_capacity=9, available_seats=9,
        range_km=5000, baggage_capacity_kg=600, cabin_configuration="charter",
        amenities=("wifi",), status="available", current_location="MUC",
        next_available_at=None,
    ),
]

# Base per-passenger economy price (EUR) used to derive deterministic pricing
# by route "distance band." Not real fares — clearly a MOCK model.
ROUTE_BASE_PRICE: dict[tuple[str, str], int] = {}
_SHORT_HAUL = 140
_MEDIUM_HAUL = 320
_LONG_HAUL = 620


def base_price_for_route(origin: str, destination: str) -> int:
    o, d = AIRPORTS.get(origin), AIRPORTS.get(destination)
    if not o or not d:
        return _MEDIUM_HAUL
    same_continent_proxy = {
        "Germany", "France", "United Kingdom", "Netherlands", "Spain", "Italy",
    }
    if o.country in same_continent_proxy and d.country in same_continent_proxy:
        return _SHORT_HAUL
    if {o.country, d.country} & {"United Arab Emirates", "Qatar", "Turkey"}:
        return _MEDIUM_HAUL
    return _LONG_HAUL


def resolve_city_or_iata(text: str) -> tuple[str, ...] | None:
    """Given free text ('Frankfurt', 'FRA', 'london'), return matching IATA
    code(s). Returns None if nothing matches; returns a multi-element tuple
    when the input is ambiguous (e.g. 'london') so the caller can ask the
    customer to disambiguate rather than guessing."""
    key = text.strip().upper()
    if key in AIRPORTS:
        return (key,)
    key_lower = text.strip().lower()
    if key_lower in CITY_TO_AIRPORTS:
        return CITY_TO_AIRPORTS[key_lower]
    return None
