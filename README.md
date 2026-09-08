# Charter123 AI

An airline AI voice customer-service and booking platform: a Vapi voice
agent backed by a FastAPI + PostgreSQL + Redis booking system, with a
Next.js frontend. Provider-agnostic by design — the whole system runs
against a fully-featured `MockAirlineProvider` with zero external aviation
credentials, and switching to a real GDS (Amadeus/Sabre) is a config
change, not a rewrite. See `docs/AIRLINE_PROVIDER.md`.

**Current status (corrected 2026-09-08 — T-3): Phases 1–5 of the build
are complete (repo/infra → DB schema & mock provider → core booking
flows → authentication/RBAC/security → Vapi voice integration), plus
Phase 7 Milestone 1 (Stripe payment sessions — labeled "Phase 6
Milestone 1" in its own handoff; see `docs/PROJECT_ROADMAP.md` §6.1 for
why that label doesn't match the original spec's numbering) and
`refund_payment` (T-3, the remainder of Phase 7). Still not built: live
telephony connection (the rest of Phase 6), real email/SMS
notifications, and the admin dashboard.** See
`docs/PROJECT_ROADMAP.md` for the full reconciled status and
`docs/PRODUCTION_CHECKLIST.md` for the exact, honest, line-by-line
status — including which parts have been executed and verified versus
written but not yet run — and `docs/SECURITY.md` for the security
architecture.

## Architecture

```
apps/web   Next.js frontend (a status page plus Phase 4's login/register/
           account pages — no booking or admin UI yet)
apps/api   FastAPI backend — flights, aircraft, bookings, passengers
docs/      Architecture, provider, booking-flow, env-var, and checklist docs
```

Full write-up: `docs/ARCHITECTURE.md`.

## Requirements

- Docker + Docker Compose (recommended path), **or** Python 3.12+ and
  Node 22+ for running the two apps directly
- Nothing else — `AIRLINE_PROVIDER=mock` by default, so there's no
  external account or API key needed to get the whole system running

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000 (interactive docs at `/docs`)
- Web: http://localhost:3000
- Mailhog (future email testing): http://localhost:8025

Then, in a second terminal, run migrations and seed reference data:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m app.db.seed
```

## Quick start (without Docker)

```bash
# Backend
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example ../../.env   # DATABASE_URL defaults to a local SQLite file if you skip this
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload

# Frontend, in a second terminal
cd apps/web
npm install
npm run dev
```

## Testing

The core domain logic (the mock GDS simulation, date resolution, PNR
generation, idempotency), the entire Phase 4 security core (password
policy, RBAC, IDOR-prevention/ownership, rate limiting, booking
verification, CSRF, redaction, Vapi tool authorization), the Phase 5 Vapi
webhook/tool-call core (argument mapping, webhook auth, rate-limit
keying, tool registry consistency), and the Phase 6 Milestone 1 payment
core (state machine, mock Stripe provider, payment argument mapping) all
have **zero third-party dependencies** and run with nothing but the
standard library:

```bash
cd apps/api
python3 -m unittest tests.test_core_logic tests.test_security_core tests.test_vapi_core tests.test_payments_core -v
```

This is **236 tests and they pass** — actually run, repeatedly, while
building each phase (123 through Phase 4, +56 in Phase 5, +44 in Phase 6
Milestone 1, +13 in T-3's `refund_payment`). Execution caught real bugs
each time, not just in Phase 1-3: a flight-ID parser that broke on
ISO-date hyphens, an
unrealistic flight-duration formula, an IDOR bug in the Phase 4
authorization logic that would have let any customer reach any other
customer's booking, a mutable-object aliasing bug in the rate limiter, and
a `cryptography` version pin that excluded the only versions with the
Argon2id support Phase 4's password hashing depends on. See the top of
`tests/test_core_logic.py`, `tests/test_security_core.py`,
`tests/test_vapi_core.py`, `tests/test_payments_core.py`, and
`PROJECT_HANDOFF_PHASE_4.md` §5 for the full bug list.

Once you've `pip install -r requirements.txt`'d, the rest of the test
pyramid — `pytest`, FastAPI `TestClient`, real-DB integration tests
(`tests/test_api_security.py` already exists and is written against this
exact stack, it just can't run here), Playwright E2E — is the natural next
layer.

## Environment variables

See `docs/ENVIRONMENT_VARIABLES.md`. Everything is read in one place:
`apps/api/app/core/config.py`. `APP_ENV=production` fails fast at startup
if anything required is missing rather than silently running unsafely.

## Database

PostgreSQL is authoritative for bookings/customers/passengers/audit logs
(SQLite is used as a zero-setup local-dev fallback — same models, same
migrations, same code). Redis is used for idempotency/caching, with an
in-process fallback for local dev when `REDIS_URL` is unset. Neither
fallback is appropriate for production — see `docs/ARCHITECTURE.md`.

## What's next

**Corrected 2026-09-08** — this section previously described the Vapi
layer, Stripe payments, and `refund_payment` as future work; all three
are now built (see "Current status" above). Read
`docs/PROJECT_ROADMAP.md` §7/§8 for the current, accurate execution plan
and position; short version: get the FastAPI/SQLAlchemy test layer
actually running somewhere with network access (nothing in that layer
has ever been executed, including T-3's refund changes), then either
connect a real phone number (the remaining piece of Phase 6) or start
Phase 8 (notifications) — neither blocks the other. **Read
`docs/SESSION_PROMPT.md` before starting any new session** — it replaces
the old advice to read
a specific phase handoff, since which handoff is "latest" now changes
over time.

## Troubleshooting

- **`docker compose up` fails to pull images** — this was written and
  reviewed but never actually run (the build environment had no Docker or
  network access); please report back what breaks so it can be fixed.
- **API won't start locally** — check `DATABASE_URL` in `.env`; the
  default SQLite fallback should work with zero setup.
- **Frontend shows "API unreachable"** — the backend isn't running, or
  `NEXT_PUBLIC_API_URL` doesn't point at it.
