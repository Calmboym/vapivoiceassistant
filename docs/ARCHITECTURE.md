# Architecture

> **2026-09-07 audit note:** this file previously said Phases 1–3 were
> the extent of what's built, and that "everything from §5 onward" was
> not yet built. That was stale — Phase 4 (auth/RBAC/security), Phase 5
> (Vapi), and Phase 7 Milestone 1 (payments) are all complete. Fixed
> below. For current, line-by-line status and the full phase-by-phase
> history, see `docs/PROJECT_ROADMAP.md` (canonical) and
> `docs/PROJECT_STATE.md` (fast lookup) — this file stays focused on
> *why* the architecture looks the way it does, not on status tracking.

## What's implemented

```
apps/web (Next.js)  →  apps/api (FastAPI)  →  AirlineProvider  →  MockAirlineProvider
      │                       │               PaymentProvider  →  MockPaymentProvider /
      │                       │                                    StripePaymentProvider
   Auth pages            Auth/RBAC/session
  (login/register/       middleware, Vapi
   account)               webhook + 21
                           tool schemas
                              │
                              ├── PostgreSQL (bookings, customers, passengers,
                              │    airports, aircraft, users, sessions, calls,
                              │    tool_executions, payments, idempotency_keys,
                              │    audit_logs)
                              └── Redis (idempotency locks, rate-limit counters,
                                   cache — falls back to an in-process store in
                                   dev if REDIS_URL is unset)
```

Flight search/quote/booking/cancel/modify (Phase 1-3), authentication/RBAC/
security hardening (Phase 4), the Vapi webhook and tool layer (Phase 5),
and payment-session creation via Stripe Checkout (Phase 7 Milestone 1,
labeled "Phase 6 Milestone 1" in its own handoff — see
`docs/PROJECT_ROADMAP.md` §6.1 for why) are all built and covered by the
dependency-free test suite. Not yet built: live telephony connection
(the remainder of Phase 6), `refund_payment` (Phase 7 remainder),
notifications (Phase 8), the admin dashboard (Phase 9), and the
Playwright/E2E/voice test suites (Phase 10). See
`docs/PRODUCTION_CHECKLIST.md` for the exact line-by-line status against
the spec's 80-item "definition of done."

## The one architectural decision worth explaining: where "flights" live

The spec's §28 lists `flights`, `flight_segments`, and `fares` as their own
database tables. This codebase deliberately does **not** persist those —
here's why, and what to do if you disagree.

An airline's schedule and live availability is inherently provider-owned
data: caching it in our own DB risks serving stale seats/prices, and a real
GDS integration (Amadeus/Sabre) would actively discourage it. So:

- **`AirlineProvider`** (app/providers/airline/base.py) is the single
  source of truth for flights, fares, and aircraft *availability*.
  `MockAirlineProvider` simulates this with deterministic, seeded
  generation — see AIRLINE_PROVIDER.md.
- **Our own Postgres** is the source of truth for *our* business
  records: `bookings`, `booking_passengers`, `customers`, `airports`
  (a small, genuinely-ours reference table used for disambiguation:
  "London" → LHR/LGW/STN/LTN), `aircraft` (a fleet reference table for
  admin display — separate from the provider's own live availability
  numbers), `idempotency_keys`, and `audit_logs`.

A `Booking` row stores an itinerary **snapshot** (origin, destination,
flight number, departure/arrival, price) taken at booking time, so booking
status/lookup (§14) never depends on the provider still remembering
anything. If you need a searchable cache of provider flight data later
(e.g. for search-result analytics), add a `flights` table as a cache in
front of the provider — not as its replacement.

## Request flow: creating a booking

1. `POST /api/v1/flights/search` → `FlightService` → `AirlineProvider.search_flights()`
2. `POST /api/v1/flights/quote` → `AirlineProvider.get_fare_quote()` (quote lives in
   the provider's memory for 15 minutes, mirroring a real GDS fare-lock window)
3. `POST /api/v1/bookings` → `BookingService.create_booking()`:
   a. Checks the idempotency store first (§27) — a retried request with the
      same key replays the stored result instead of double-booking.
   b. Calls `AirlineProvider.create_booking()` — this is where a real
      adapter would actually call Amadeus/Sabre.
   c. Persists our own `Booking` + `BookingPassenger` rows with a fresh PNR.
   d. Writes an `AuditLog` row.

Every step that changes state (create/modify/cancel) requires the caller to
have already gotten an explicit "yes" from the customer — see
BOOKING_FLOW.md and §60 of the original spec ("the LLM is never the source
of truth").

## Trust boundary

Updated 2026-09-07 — Phase 4 (auth/RBAC) and Phase 5 (Vapi) are both
built now, so this section describes the actual current boundary rather
than warning about a state before either existed.

**The real Vapi path is authenticated properly.** `POST /api/v1/vapi/
webhook` (`app/api/routes/vapi.py`) checks a shared secret
(`VAPI_WEBHOOK_SECRET`) before doing anything else, and only then derives
`call_id` from the *webhook body itself* (`message.call.id`) — never from
a client-controlled header. Tool-call authorization runs through
`authorize_vapi_tool_call()` against the `TOOL_AUTHORIZATION_MATRIX`
(`app/core/security/vapi_authorization.py`), and web-facing routes run
through `authorize_resource_access()`/session auth
(`app/core/security/{rbac,ownership}.py`, `app/api/deps_auth.py`).

**One real, if minor, residual gap found by the 2026-09-07 audit:**
`app/api/routes/bookings.py::_actor_for()` still reads
`x-charter123-call-id` straight off the request header, **unauthenticated**,
on the *direct* REST booking routes (as opposed to the Vapi webhook path
above) — but only to build the audit log's human-readable `actor` string
(e.g. `vapi_call:{call_id}`), never for an authorization decision. This
doesn't unlock anything a caller couldn't otherwise do, but it is exactly
the client-supplied-identifier pattern spec §20 warns against ("Never
trust x-user-id, customerId, bookingId, or similar client-supplied
identifiers"), and it means a forged header can make the audit log
misattribute a booking action to a call that didn't actually make it —
including a real call's ID, if guessed or observed. See
`docs/PROJECT_ROADMAP.md` §6.6 for the full writeup and
`docs/WORK_BREAKDOWN_STRUCTURE.md` WBS-6.4 for the fix, which hasn't been
made yet.
