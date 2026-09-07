# Airline Provider

## Switching providers

Set `AIRLINE_PROVIDER` in `.env` to `mock`, `amadeus`, or `sabre`. That's
the only code path that decides which implementation runs —
`app/providers/airline/__init__.py::get_airline_provider()`. Nothing else
in the app imports a concrete provider class directly.

## MockAirlineProvider

Lives entirely in `app/providers/airline/mock.py` +
`reference_data.py`, and has **zero third-party dependencies** — it only
uses the Python standard library. That's deliberate: it means the trickiest
logic in the whole system (deterministic flight generation, fare math,
tiered cancellation fees, idempotent booking/cancellation) can be
unit-tested with nothing but `python3 -m unittest`, with no `pip install`
required. Run it yourself:

```bash
cd apps/api
python3 -m unittest tests.test_core_logic -v
```

Design notes:

- **Flights are a pure function of `(origin, destination, date, index)`.**
  `search_flights()` and a later `get_flight(flight_id)` always agree on
  the same flight's price/schedule without a shared database, because the
  flight_id itself encodes the seed (`MOCK_{origin}_{destination}_{date}_{index}_{cabin}`
  — note the `_` separator; an earlier version used `-`, which broke
  because ISO dates contain hyphens too — see the comment in `mock.py`).
- **Quotes and bookings need real memory** (a quote expires; a booking
  gets modified), so those live in the `MockAirlineProvider` instance's
  `_quotes` / `_bookings` dicts. This is appropriate for MOCK mode and
  explicitly *not* how the app's own booking data is stored — see
  ARCHITECTURE.md for why `bookings` is a real Postgres table instead.
- **Pricing** is a deterministic function of great-circle distance (via a
  proper haversine calculation — not a placeholder), a per-cabin
  multiplier, and a per-search seeded jitter. It is realistic enough to be
  useful (e.g. FRA→DXB comes out around €280–390/economy seat, ~6.5h
  flight time) but is not real airline pricing.
- **Cancellation fees** rise the closer you get to departure: 10% at
  >7 days out, 25% at 2–7 days, 50% at 24–48h, 90% inside 24h.

## Implementing a real provider (Amadeus / Sabre)

`app/providers/airline/amadeus.py` and `sabre.py` exist as **placeholders
only** — every method raises `NotImplementedError`. This is intentional:
no credentials or API documentation for either were available when this
codebase was generated, and the build spec is explicit that undocumented
APIs must never be fabricated (§5/§40).

To implement one for real:

1. Get real credentials (Amadeus for Developers / Enterprise, or Sabre
   Dev Studio) and read their actual API docs.
2. Fill in `AIRLINE_API_BASE_URL`, `AIRLINE_API_KEY`, `AIRLINE_API_SECRET`
   (+ `AIRLINE_CLIENT_ID`/`_SECRET` if the provider uses OAuth2 client
   credentials) in `.env`.
3. Implement each `AirlineProvider` method against the real endpoints,
   translating their response shapes into the exact same dataclasses
   `MockAirlineProvider` returns (`FlightOffer`, `FareQuote`,
   `ProviderBooking`, etc., all defined in `base.py`). Nothing above the
   provider layer should need to change.
4. Translate the real API's error responses into the `ProviderError`
   subclasses in `base.py` so `app/core/exceptions.py`'s handling — which
   turns provider errors into the standard `{success, error, request_id}`
   envelope — keeps working unmodified.
5. Populate `ProviderCapabilities` accurately (does this provider support
   hold-bookings? seat selection? charter?) — the application is meant to
   read this and adapt (§69), though that adaptation logic isn't wired up
   in the UI/services yet in this phase.
6. Set `AIRLINE_PROVIDER=amadeus` (or `sabre`) and re-run the test suite —
   `tests/test_core_logic.py` will need a parallel (network-mocked)
   version for the new adapter; it currently only covers MOCK mode.
