# Charter123 — Phase 4 Engineering Handoff

**Read this entire document before modifying the repository.** It exists so
a new AI coding session — a different chat, possibly a different model —
can continue this project without re-deriving decisions already made,
re-discovering bugs already found and fixed, or re-litigating architecture
already settled. If something below conflicts with what you observe in the
repository, trust the repository and flag the discrepancy; this document
was written carefully against the actual code, but it is still prose, not
the source of truth.

---

## 1. Project identity

**Name:** Charter123 AI. **Purpose:** a production-grade charter/airline
booking platform with a future AI voice-agent front end. **Product
concept:** a caller (phone, via Vapi) or a web visitor searches flights,
gets a fare quote, books, and can later look up, modify, or cancel that
booking — all through either a conversational voice agent or a
conventional web app, backed by the same authorization-hardened API.
**Target users:** individuals booking charter flights, plus (eventually)
human support/booking/finance staff and admins operating the same system
through role-gated tools. **Current milestone:** Phase 4 of a 10-phase
build. **Current status:** Phase 4 code-complete, tested as far as this
build sandbox allows (see §4). **Long-term objective:** a fully-featured
voice-first booking platform — search, quote, book, modify, cancel,
passenger management, payment, and support handoff, all reachable by phone
through a Vapi assistant that is authorized exactly like any other actor
in the system, never treated as an administrator.

Provider-agnostic by design: the whole system runs against a
`MockAirlineProvider` with zero external aviation credentials; switching to
a real GDS (Amadeus/Sabre) is meant to be a config change, not a rewrite
(`docs/AIRLINE_PROVIDER.md`).

## 2. Current milestone

**PHASE 4 — AUTHENTICATION, AUTHORIZATION & SECURITY**

Status: **COMPLETE, BUT EXTERNAL/RUNTIME INFRASTRUCTURE UNVERIFIED.**

Precisely: every piece of Phase 4 the original spec asked for has been
designed and implemented. The framework-agnostic security core
(`app/core/security/*.py` — RBAC, ownership/IDOR prevention, password
hashing+policy, tokens, rate limiting, CSRF, redaction, booking
verification, Vapi tool authorization) is not just written but **actually
executed, 93/93 passing**, in this build sandbox, with zero third-party
dependencies. The FastAPI/SQLAlchemy layer built on top of it (models,
migration, repositories, services, routes, middleware, admin bootstrap) is
written completely and correctly against the real APIs used elsewhere in
this codebase, but has **not been executed** — this sandbox has no network
access to `pip install fastapi/sqlalchemy/pydantic/pytest`. Do not
represent this phase as "fully tested end-to-end"; represent it exactly as
above.

## 3. What is implemented

### Phase 1-3 (unchanged this phase, re-confirmed working)
- Repository/infra scaffold (monorepo: `apps/api`, `apps/web`, `docs/`)
- FastAPI + SQLAlchemy + PostgreSQL(+SQLite fallback) + Redis(+in-process
  fallback) backend foundation
- Next.js/TypeScript frontend foundation (one status page pre-Phase-4)
- `AirlineProvider` interface + `MockAirlineProvider` (fully-featured,
  deterministic) + placeholder Amadeus/Sabre adapters that fail loudly
  rather than fabricate
- Flight search, fare quotes, booking creation, booking lookup (with a
  factor-check verification), modification, cancellation, passenger
  management (add/remove, recomputes price)
- PNR generation (haversine-based duration calc, fixed a real bug found by
  execution: an earlier formula put FRA→DXB at 14+ hours; it's ~6h32m now)
- Idempotency (application-level store + provider-level)
- Audit logging (`AuditLog` model + `record_audit_event()`)
- Passport field encryption (Fernet via `cryptography`, dev fallback with
  a loud `UNENCRYPTED-DEV:` prefix and warning if no key is set)
- Date resolution, airport/aircraft reference data

### Phase 4 (this phase)
- `User` model (login-capable identity, separate from `Customer` — see §6)
- Argon2id password hashing (`cryptography`'s native KDF, not
  `argon2-cffi` — see §5's bug #3), password strength policy
- `POST /auth/{register,login,logout,logout-all,refresh,change-password,
  request-password-reset,reset-password}`, `GET /auth/me`
- Sessions: opaque random tokens, only the SHA-256 hash persisted, rotated
  (not just extended) on refresh, individually or all-at-once revocable
- RBAC: 7 roles × 25 permissions (`app/core/security/rbac.py`), DB-backed
  assignment (`roles`/`permissions`/`role_permissions`/`user_roles` tables,
  seeded by `app/db/seed.py::seed_rbac()`)
- Customer ownership / IDOR prevention (`app/core/security/ownership.py`)
  — wired into every booking/passenger route
- Booking verification state machine + `POST /bookings/{pnr}/verify` —
  closes the real gap where cancel/modify trusted only a client-supplied
  boolean (see §5's bug #1)
- Vapi security preparation: `VAPI_AGENT` actor type + tool-authorization
  matrix — architecture only, no live Vapi code
- Admin bootstrap script (env-gated, no hard-coded credentials)
- Rate limiting (fixed-window + progressive account lockout) with the
  exact profiles the spec named
- CSRF (signed, session-bound double-submit cookie) + middleware
- Security headers middleware
- Centralized log redaction (recursive, depth-capped, secret-value-pattern
  scanning) — Phase 1-3's `_redact_processor` now delegates to it
- Audit logging extended with auth/RBAC event types
- Frontend auth foundation: login/register/account pages, `AuthContext`,
  a UX-only Next.js middleware route guard
- `docs/SECURITY.md`, this handoff document, `docs/PRODUCTION_CHECKLIST.md`
  updated

## 4. Test results

**Exact, final, re-run after every change in this phase — not carried over
from an earlier claim:**

```
python3 -m unittest tests.test_core_logic tests.test_security_core -v
...
Ran 123 tests in ~0.2s
OK
```

- `tests.test_core_logic` — **30/30 PASS** (Phase 1-3, unchanged,
  zero dependencies).
- `tests.test_security_core` — **93/93 PASS** (Phase 4 security core,
  zero dependencies) — RBAC, ownership/IDOR (including the mandatory §33
  Critical Security Test), password policy, password hashing (real
  Argon2id, not a stand-in — see §5), tokens, rate limiting/lockout,
  booking verification state machine, CSRF, redaction, Vapi tool
  authorization, error codes.
- `tests.test_api_security` — **0 run, 6 classes / 18 methods SKIPPED**
  (`OK (skipped=6)`), not failed, not falsely claimed as passing — needs
  `fastapi`+`sqlalchemy`+`pydantic`+`pytest`, none installable here (no
  network). Written completely and correctly against the real
  `TestClient`/SQLAlchemy APIs; covers registration, login/logout/
  logout-all/refresh, password change/reset, the HTTP-level Critical
  Security Test (forged `x-user-id` header included), CSRF
  accept/reject, rate-limit-triggers-429, and an audit-log-row assertion.
- **BLOCKED, not run at all:** anything needing Docker, PostgreSQL, Redis,
  `npm install`, `alembic upgrade head` for real, or a live Vapi/Stripe
  call — same infrastructure gap Phase 1-3 already had, unchanged by this
  phase.

Do not report these numbers again without re-running them if you change
anything in `app/core/security/*.py`, `app/models/*.py`, or the migration.

## 5. Bugs found during development

All four were caught by **actually running the tests**, not by code
review — this is worth internalizing as a working method, not just a fact
about this codebase.

### Bug 1 — IDOR: any customer could reach any other customer's booking
**What was wrong:** `app/core/security/ownership.py`'s
`authorize_resource_access()` checked "does this HUMAN_USER actor hold
`staff_permission`" *before* checking ownership. Because the bare
`CUSTOMER` role also grants `bookings.read`/`bookings.cancel`/etc. (a
customer needs that permission for their *own* bookings), that check
returned `ALLOW` for any authenticated customer against any *other*
customer's booking — the permission string was identical for both scopes,
and the code had no way to distinguish "granted via a staff role" from
"granted via bare CUSTOMER."
**Detection:** `tests/test_security_core.py::CriticalSecurityTest` and
`OwnershipTests` — specifically `test_non_owner_customer_denied`,
`test_get/modify/cancel_booking_b_as_customer_a_denied`, and
`test_forged_x_user_id_header_has_no_effect` all failed with "True is not
false" on first run.
**Fix:** reordered to check ownership first; non-owner access now
additionally requires `actor.is_staff` (any role beyond bare `CUSTOMER`),
not permission-string membership alone. Full code comment at the top of
`authorize_resource_access()`.
**Impact:** this was the actual security property the entire phase exists
to guarantee. If shipped as it initially stood, Customer A could have
read, modified, or cancelled Customer B's booking simply by being logged
in as any customer at all.

### Bug 2 — mutable dataclass aliasing in the rate limiter
**What was wrong:** `BackoffLockout.record_failure()` returned the
`FailureState` object it had just mutated. `InMemoryRateLimitStore`
returns the *same object reference* on every `get`/`set` round-trip (no
copying), so two successive `record_failure()` calls in a test both ended
up holding the *same, further-mutated* object — making "backoff increases
with each failure" appear false even though the underlying counting logic
was correct.
**Detection:** `BackoffLockoutTests::test_backoff_increases_and_is_capped` —
`s1.locked_until` and `s2.locked_until` compared equal when they should
have differed.
**Fix:** return `dataclasses.replace(state)` (a snapshot) instead of the
live, store-owned reference.
**Impact:** would not have caused a security failure (the store's own
state was correct), but would have made the actual lockout *behavior*
different from what any test or code review suggested — a "the code lies
about what it does" class of bug, exactly what execution-based testing
catches and inspection doesn't.

### Bug 3 — `cryptography` version pin excluded Argon2id entirely
**What was wrong:** `app/core/security/passwords.py` uses
`cryptography.hazmat.primitives.kdf.argon2.Argon2id` (a deliberate choice
over `argon2-cffi`, which can't be installed in this sandbox — see §9).
`requirements.txt` pinned `cryptography>=43.0,<44.0`. Argon2id support was
added in `cryptography` **44.0.0** ("Added support for Argon2id when using
OpenSSL 3.2.0+," per the project's own published changelog). The pin as
written explicitly *excluded every version that has the feature the code
depends on* — following it in a real environment would have made password
hashing fail to import at all.
**Detection:** not a test failure — caught by deliberately cross-checking
the real pyca/cryptography changelog (via web search) against the pin
while writing this handoff section, after noticing the sandbox's installed
version (46.0.6) had the feature but the *pinned range* didn't obviously
guarantee it.
**Fix:** `requirements.txt` now pins `cryptography>=44.0,<47.0`.
**Impact:** would have been a hard, immediate failure the first time
anyone actually tried to run this — the worst kind of bug to ship, because
it's invisible until the exact moment someone follows the setup
instructions.

### Bug 4 — password-policy email check compared the full address, not the local part
**What was wrong:** `app/core/security/password_policy.py` checked
`email.lower() in password.lower()` — but a password containing just the
local part (`"janedoe123..."` for `janedoe@example.com`) doesn't literally
contain the full string `"janedoe@example.com"`, so this never fired.
**Detection:** `PasswordPolicyTests::test_contains_email_rejected` failed.
**Fix:** extract the local part (before `@`) and check that instead.
**Impact:** minor — a password-strength nicety, not an authorization
boundary — but the fix is in place and tested.

### Pre-existing Phase 1-3 issue noted, not fixed (out of scope)
`customers.email` is `unique=True, index=True` in the model but the
hand-written `0001_initial_schema.py` migration has neither. Found while
cross-checking migration 0002 against its own models for consistency
(clean: 47/47 real columns present) and then checking 0001 the same way
for comparison. Not fixed — unrelated to auth, and Phase 4's instructions
were to fix real *auth-hardening* gaps, not rewrite unrelated Phase 1-3
migrations. Worth a one-line fix before `Customer.email` uniqueness is
relied on anywhere.

## 6. Security model

See `docs/SECURITY.md` for the full writeup (21 sections: auth
architecture, sessions, identity model, RBAC, ownership, booking
verification, Vapi prep, rate limiting, CSRF, CORS, headers, secrets,
passport-encryption audit, redaction, audit logging, request correlation,
error codes, enumeration trade-offs, GDPR notes, incident-response notes,
known limitations). Summary of the identity model specifically, since it's
the one piece a new session is most likely to get wrong by assumption:

`User` (Phase 4, login-capable) and `Customer` (Phase 1-3, a booking
contact record created ad-hoc with no password) are **separate models on
purpose**. A caller can still book without ever creating an account — that
has to keep working for the voice channel. `User.customer_id` is an
optional FK, populated once a customer registers/links an account;
staff/admin `User`s never get one. `CurrentActor.customer_id` (session-
derived, never request-derived) is what every ownership check compares
against a resource's actual `customer_id`.

## 7. IDOR / authorization model

Enforced in exactly one place: `app/core/security/ownership.py`'s
`authorize_resource_access()` (and its typed wrappers
`authorize_booking_access`, `authorize_passenger_access`,
`authorize_customer_profile_access`, `authorize_payment_access`). These
functions take a `CurrentActor` and a resource's *actual* owner id (always
loaded from the DB by primary key/PNR, never from a request body/header) —
there is **no parameter** a client-supplied `x-user-id`/`userId`/
`customerId` could occupy, and
`test_authorize_booking_access_signature_has_no_client_identity_parameter`
asserts this structurally (inspects the function signature, not just its
behavior), specifically so a future refactor can't "helpfully" reintroduce
a header-trusting branch without a test breaking.

`app/api/deps_auth.py::get_current_actor` is the **only** place in the
codebase that constructs a `CurrentActor` from an HTTP request, and it
reads the session cookie — nothing else. Every route handler that touches
a booking/passenger/customer resource calls `require_booking_access`/
`require_passenger_access`/`require_customer_profile_access` (thin HTTP
wrappers around the functions above) immediately after loading the
resource and before calling any service method.

The bug described in §5.1 is the concrete story of what happens when this
discipline slips even slightly (checking a permission before checking
ownership) — read that section if you're about to touch this file.

## 8. Booking verification

```
VERIFICATION_PENDING --(factor matched)-------> VERIFIED
VERIFICATION_PENDING --(factor wrong, attempts<max)--> VERIFICATION_PENDING
VERIFICATION_PENDING --(factor wrong, attempts>=max)--> FAILED
VERIFICATION_PENDING --(expires_at passed)-----> EXPIRED
```

- **Identifies the booking:** `booking_id` (the DB row's UUID, not the
  PNR — PNR is what the *caller* provides; `booking_id` is looked up from
  it server-side).
- **Identifies the actor:** for a human, the session; for the future Vapi
  actor, `call_id` (§9) — a verification token is scoped to exactly one
  `(call_id, booking_id, purpose)` triple.
- **Factors:** email-or-phone + last-name (`BookingVerificationService.
  verify()`, Phase 1-3, unchanged) — a policy decision the backend
  enforces, not something an LLM/caller gets to choose.
- **Expiry:** 10 minutes by default (`DEFAULT_TTL`,
  `app/core/security/verification.py`), checked on every use, not just at
  issuance.
- **Scoping:** `purpose` matters — a token verified for `"view_booking"`
  does not authorize `"cancel_booking"`. Terminal states (`VERIFIED`,
  `FAILED`, `EXPIRED`) are never re-entered even if a later factor-check
  would have matched — `test_terminal_session_cannot_be_rescored` covers
  this explicitly.
- **Vapi future use:** Phase 5's webhook handler, on each tool call,
  should call `VerificationSessionService.check(raw_token=..., booking_id=
  ..., purpose=<tool-specific>)` and only proceed if it returns `True` —
  the same function the web-facing routes already use. Do not build a
  second verification mechanism for Vapi specifically.

## 9. Vapi readiness

**Do NOT read this section as "Vapi integration is complete." It is not.**

### Already implemented
- `ActorType.VAPI_AGENT` as a distinct actor type — its permission set is
  always exactly `{"vapi.execute"}`, by construction (nothing assigns it
  more).
- `app/core/security/vapi_authorization.py::VAPI_TOOL_MATRIX` — every
  planned tool classified `PUBLIC` / `REQUIRES_VERIFIED_BOOKING` /
  `STAFF_OR_ADMIN_ONLY` (the last always denies a Vapi actor).
- `authorize_vapi_tool_call()` — the function Phase 5's webhook handler
  should call for every tool invocation, fully unit-tested
  (`VapiAuthorizationTests`, 8 tests) including "unauthenticated Vapi
  request rejected," "authenticated + unverified booking + sensitive tool
  rejected," "authenticated + verified booking + allowed tool → allowed,"
  and "verified for booking X still denied for booking Y."

### Architecture prepared, not implemented
- The Vapi webhook route itself (signature verification, request parsing,
  `call_id`/`assistant_id` extraction into a real `CurrentActor`).
- The tool-call HTTP endpoints Vapi would actually invoke (they don't
  exist as Vapi-specific routes — the *booking* routes exist and are
  authorized; a Vapi tool handler would call into the same services, not
  duplicate them).
- Vapi Assistant configuration, system prompt, tool JSON schemas.

### Not implemented / requires external access
- A live Vapi account, phone number, or webhook secret — nothing here has
  ever talked to Vapi's actual API.
- Anything voice-specific: call recording, transcription, multilingual
  support, human-transfer flows.

## 10. Next phase starting point — PHASE 5: VAPI VOICE AGENT

Build, in order:
1. **Vapi tool JSON schemas** for each tool in §11 below, matching the
   request/response shapes the existing service layer already expects
   (e.g. a `cancel_booking` tool's arguments should map directly onto
   `BookingCancelRequest`).
2. **Vapi webhook route** (`app/api/routes/vapi.py`, new) — verifies the
   webhook signature (never trust an unsigned payload), builds a
   `CurrentActor(actor_type=VAPI_AGENT, ...)` from verified context, and
   for anything beyond a `PUBLIC` tool, calls
   `authorize_vapi_tool_call()` before doing anything else. This function
   should be *thin* — see `app/api/deps_auth.py`'s own docstring about
   keeping HTTP-layer files free of actual authorization logic.
3. **Vapi Assistant configuration + system prompt** — the prompt should
   instruct the assistant to call `POST /bookings/{pnr}/verify` before
   attempting any sensitive tool, but the *enforcement* is
   `authorize_vapi_tool_call()`, not the prompt. Do not let the prompt
   become the security boundary.
4. **conversation state / call_id threading** — every tool call in one
   phone call should share one `call_id`, which is also what scopes
   verification sessions (§8).
5. Voice confirmation, human transfer, error recovery, multilingual
   support, call recording/privacy — after the above, in whatever order
   the actual spec for Phase 5 prioritizes them.

Do not implement any of this in the current session unless you are
starting Phase 5 with the user's explicit go-ahead.

## 11. Future Vapi tool list

| Tool | Purpose | Authz requirement | Booking verification? | Confirmation? | Mutates? | Needs external infra? |
|---|---|---|---|---|---|---|
| `search_flights` | Find flights | Public | No | No | No | No (mock provider) |
| `get_flight_details` | Flight info | Public | No | No | No | No |
| `get_aircraft_availability` | Fleet check | Public | No | No | No | No |
| `get_fare_quote` | Price a flight | Public | No | No | No | No |
| `get_booking` | Read a booking | Verified booking or staff | Yes | No | No | No |
| `verify_booking_customer` | Run the verification flow | Public (it's what *produces* verification) | N/A | No | No | No |
| `create_booking` | New booking | Public (no prior owner to verify against) | No | Yes (price/fee ack) | Yes | No |
| `update_booking` | Modify | Verified booking or staff | Yes | Yes | Yes | No |
| `cancel_booking` | Cancel | Verified booking or staff | Yes | Yes (fee ack) | Yes | No |
| `get_cancellation_policy` | Quote fee | Public (read-only) | No | No | No | No |
| `get_baggage_policy` | Info | Public | No | No | No | No |
| `add_baggage` | Add baggage | Verified booking or staff | Yes | Maybe | Yes | Not yet modeled |
| `get_seat_options` | Read | Verified booking or staff | Yes | No | No | Not yet modeled |
| `select_seat` | Pick a seat | Verified booking or staff | Yes | No | Yes | Not yet modeled |
| `add_passenger` | Passenger mgmt | Verified booking or staff | Yes | Maybe | Yes | No |
| `update_passenger` | Passenger mgmt | Verified booking or staff | Yes | Maybe | Yes | No |
| `remove_passenger` | Passenger mgmt | Verified booking or staff | Yes | Yes | Yes | No |
| `create_payment_session` | Start payment | Verified booking or staff | Yes | Yes | Yes | **Yes — Stripe** |
| `get_payment_status` | Read payment | Verified booking or staff | Yes | No | No | Yes — Stripe |
| `send_confirmation` | Notify | Staff/system only | N/A | No | Yes (side effect) | Yes — email/SMS provider |
| `send_sms` | Notify | Staff/system only | N/A | No | Yes | Yes — Twilio |
| `send_email` | Notify | Staff/system only | N/A | No | Yes | Yes — Resend |
| `create_support_ticket` | Escalate | Verified or staff | Depends | No | Yes | Not yet modeled |
| `transfer_to_human` | Escalate | Public (safety valve) | No | No | No | Yes — Vapi transfer config |
| `create_callback_request` | Escalate | Public or verified | Maybe | No | Yes | Not yet modeled |

`refund_payment` and any admin-configuration tool are `STAFF_OR_ADMIN_ONLY`
in `VAPI_TOOL_MATRIX` and are **never** reachable by a Vapi actor at all —
not listed above because they are not Vapi tools by design.

## 12. External integrations

| Integration | Current state | Required for | Credentials needed |
|---|---|---|---|
| PostgreSQL | Config + models ready; SQLite fallback works; never run against real Postgres in this sandbox | Production data | `DATABASE_URL` |
| Redis | Config + client ready; in-process fallback works; never run against real Redis here | Idempotency/rate-limit persistence across processes | `REDIS_URL` |
| Vapi | **Not integrated at all.** Authorization architecture only (§9) | Phase 5 | `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`, `VAPI_ASSISTANT_ID`, `VAPI_PHONE_NUMBER_ID` |
| Stripe | Not integrated. Settings/env vars exist, nothing calls them | Phase 7 | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| Email | `MockEmailProvider` only — records, never sends | Phase 6 (real send) | `RESEND_API_KEY` |
| SMS | Not modeled | Phase 6 | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` |
| Amadeus | **Placeholder adapter — fails loudly on any call, by design.** Never invent that this works. | Real GDS switch | `AIRLINE_API_*`, `AIRLINE_CLIENT_*` |
| Sabre | Same as Amadeus — placeholder, fails loudly | Real GDS switch | Same category |

## 13. Environment variables

Full table: `docs/ENVIRONMENT_VARIABLES.md` (kept current — read that file,
don't duplicate it here and let the two drift). Phase 4 additions:
`BOOTSTRAP_ADMIN_ENABLED` (default `false`; must be `false` in
production — enforced by `Settings.validate_for_production()`),
`BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` (both required only
when the above is `true`). `SECRET_KEY` (already existed) now also HMACs
CSRF tokens.

Development: everything defaults to something that runs with zero
external accounts (`AIRLINE_PROVIDER=mock`, SQLite fallback, in-process
Redis fallback, `MockEmailProvider`). Testing: same, plus
`APP_ENV=test` used by `tests/test_api_security.py`'s fixture. Production:
`Settings.validate_for_production()` is the authoritative list of what's
actually required — read that function, not just the env var table, before
deploying.

Secrets (never real values in `.env.example`, never committed):
`SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `DATABASE_URL` (if it embeds a real
password), `BOOTSTRAP_ADMIN_PASSWORD`, `VAPI_API_KEY`/`VAPI_WEBHOOK_SECRET`,
`STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`, `RESEND_API_KEY`,
`TWILIO_AUTH_TOKEN`, `AIRLINE_API_KEY`/`AIRLINE_API_SECRET`/
`AIRLINE_CLIENT_SECRET`.

## 14. Database migrations

- **0001_initial_schema** (Phase 1-3): `airports`, `aircraft`, `customers`,
  `bookings`, `booking_passengers`, `idempotency_keys`, `audit_logs`.
  **Known discrepancy, not fixed this phase:** `customers.email` is
  `unique=True` in the model but not in this migration — see §5's
  "pre-existing issue" note. Do not silently fix this unless asked; it's
  flagged, not resolved, on purpose.
- **0002_add_auth_rbac_tables** (Phase 4, this phase): `users`,
  `sessions`, `roles`, `permissions`, `role_permissions`, `user_roles`,
  `verification_sessions`, `password_reset_tokens`,
  `email_verification_tokens`. Cross-checked column-by-column against the
  five Phase 4 model files: 47/47 real `mapped_column()` fields present.
  Never actually run via `alembic upgrade head` in this sandbox (no
  `alembic` installed) — hand-written and checked, same caveat Phase 1-3's
  migration already carried.

Neither migration has been executed. Run `alembic upgrade head` for real
before trusting either.

## 15. Repository structure

```
apps/api/app/
  api/
    deps.py            Phase 1-3 deps (idempotency store, provider) — UNCHANGED this phase
    deps_auth.py        Phase 4: get_current_actor + every require_*() HTTP-layer auth dependency
    routes/
      auth.py            Phase 4: the 9 auth endpoints
      bookings.py        Phase 1-3, REWRITTEN this phase: authorization wired in, +verify endpoint
      passengers.py       Phase 1-3, REWRITTEN this phase: authorization wired in
      aircraft.py, flights.py, health.py   Phase 1-3, unchanged
  core/
    config.py            Phase 1-3, EXTENDED: bootstrap-admin settings
    exceptions.py         Phase 1-3, EXTENDED: RateLimitedError, AuthError
    logging.py            Phase 1-3, EXTENDED: delegates redaction to app.core.security.redaction
    security/              Phase 4, ALL NEW — the dependency-free core (see below)
    dates.py, encryption.py, idempotency.py, pnr.py   Phase 1-3, unchanged
  db/
    bootstrap_admin.py     Phase 4, new
    seed.py                Phase 1-3, EXTENDED: seed_rbac()
    migrations/versions/0002_add_auth_rbac_tables.py   Phase 4, new
    session.py, redis_client.py, migrations/versions/0001_*.py   unchanged
  middleware/              Phase 4, ALL NEW: csrf.py, security_headers.py
  models/
    user.py, session.py, rbac.py, verification.py, tokens.py   Phase 4, new
    __init__.py             Phase 1-3, EXTENDED: exports the new models
    aircraft.py, airport.py, audit_log.py, base.py, booking.py, customer.py, idempotency.py   unchanged
  repositories/
    user_repository.py, session_repository.py, rbac_repository.py,
    verification_repository.py, token_repository.py   Phase 4, new
    booking_repository.py, customer_repository.py   Phase 1-3, unchanged
  schemas/
    auth.py                 Phase 4, new
    booking.py, passenger.py   Phase 1-3, EXTENDED: verification_token fields, BookingVerifyRequest/Out
  services/
    auth_service.py, session_service.py, rbac_service.py, rate_limit_service.py,
    email_provider.py   Phase 4, new
    verification_service.py   Phase 1-3, EXTENDED: added VerificationSessionService
    booking_service.py, cancellation_service.py, passenger_service.py,
    flight_service.py, audit_service.py   Phase 1-3, unchanged
  providers/airline/   Phase 1-3, unchanged (mock + placeholder Amadeus/Sabre)
  main.py                 Phase 1-3, EXTENDED: auth router + CSRF/security-headers middleware

apps/api/app/core/security/   <- the dependency-free Phase 4 core, all new:
  actor.py            CurrentActor, ActorType — the ONE identity object
  errors.py            AuthErrorCode + HTTP status mapping
  tokens.py            secure random tokens, hashing, expiry
  password_policy.py    strength validation (no crypto dependency)
  passwords.py          Argon2id via cryptography's native KDF
  rbac.py               role -> permission matrix + resolution
  ownership.py           the IDOR-prevention authorization engine (§7)
  rate_limiter.py         fixed-window limiter + progressive lockout
  verification.py         booking verification state machine
  csrf.py                signed, session-bound double-submit tokens
  redaction.py            recursive sensitive-data redaction
  vapi_authorization.py    Vapi tool-authorization matrix (§9)

apps/api/tests/
  test_core_logic.py      Phase 1-3, unchanged, 30/30
  test_security_core.py    Phase 4, new, 93/93 — the dependency-free core, real
  test_api_security.py     Phase 4, new — FastAPI-level, written, skips cleanly here

apps/web/
  contexts/AuthContext.tsx, lib/api.ts, middleware.ts,
  app/{login,register,account}/page.tsx   Phase 4, new
  app/{page,layout}.tsx, globals.css, etc.   Phase 1-3, layout.tsx EXTENDED to wrap AuthProvider

docs/
  SECURITY.md              Phase 4, new — full architecture writeup
  PRODUCTION_CHECKLIST.md   EXTENDED — items 35-50 added for Phase 4
  ENVIRONMENT_VARIABLES.md  EXTENDED — bootstrap-admin vars
  ARCHITECTURE.md, AIRLINE_PROVIDER.md, BOOKING_FLOW.md   unchanged

PROJECT_HANDOFF_PHASE_4.md   this file, at repo root
```

## 16. How to run locally

```bash
# 1. Install
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # now correctly pulls cryptography>=44.0 — see §5 bug 3

# 2. Configure
cp ../../.env.example ../../.env
# Fill in SECRET_KEY, FIELD_ENCRYPTION_KEY at minimum for anything beyond
# the SQLite/in-process-Redis dev defaults. Leave BOOTSTRAP_ADMIN_ENABLED=false.

# 3. Start Postgres + Redis (or skip — SQLite/in-process fallbacks work for local dev)
cd ../.. && docker compose up -d postgres redis   # if using Docker

# 4. Migrate + seed
cd apps/api
alembic upgrade head
python -m app.db.seed             # now also seeds RBAC roles/permissions

# 5. (Optional) bootstrap an admin
BOOTSTRAP_ADMIN_ENABLED=true BOOTSTRAP_ADMIN_EMAIL=admin@example.com \
  BOOTSTRAP_ADMIN_PASSWORD='a genuinely strong passphrase 2026' \
  python -m app.db.bootstrap_admin
# then unset BOOTSTRAP_ADMIN_ENABLED again

# 6. Run the backend
uvicorn app.main:app --reload

# 7. Frontend, second terminal
cd apps/web
npm install
npm run dev

# 8. Tests
cd apps/api
python3 -m unittest tests.test_core_logic tests.test_security_core -v   # zero deps, should be 123/123 immediately
pytest tests/test_api_security.py -v                                     # needs step 1 done first
```

None of steps 1, 3, 5, 6, 7, or 8's `pytest` line have been executed in
this build environment — see §17.

## 17. What has not been verified

- Docker / `docker compose up --build` — never run (no Docker in this
  sandbox).
- PostgreSQL, Redis — never run against real instances.
- `npm install` / Next.js dev server / TypeScript type-checking — never
  run (no network for npm; `node`/`npm` binaries exist in this sandbox but
  package installation does not work without registry access).
- FastAPI runtime — never imported (no network to `pip install`).
- SQLAlchemy runtime, including both migrations — never imported/run.
- Alembic — never run (`alembic upgrade head` untested).
- `pytest` + FastAPI `TestClient` (`tests/test_api_security.py`) — written,
  never executed.
- Vapi live API, Stripe live API — not integrated at all (§9/§12).
- Real Argon2id load/latency characteristics under the `PasswordHasher`'s
  configured cost parameters (`time_cost=3, memory_cost=64MiB,
  parallelism=2`) — the *correctness* of hashing/verification is tested
  (§4); performance under real concurrent load is not.

## 18. Production readiness

- **CODE COMPLETE:** Yes, for everything Phase 4's spec listed.
- **TEST VERIFIED:** Partially. The security-critical *logic* (RBAC,
  IDOR/ownership, verification, rate limiting, CSRF, redaction, password
  hashing, Vapi tool authorization) — yes, 93/93 real executed tests. The
  HTTP/DB *wiring* around that logic — no, written but unexecuted.
- **INFRASTRUCTURE VERIFIED:** No. See §17.
- **EXTERNAL INTEGRATIONS VERIFIED:** N/A — none exist yet except mocks.
- **SECURITY REVIEWED:** Self-reviewed and execution-tested to the extent
  described above; not reviewed by a second party or a professional
  security auditor. Do not represent this as an independent security
  review.
- **LEGAL/GDPR REVIEW REQUIRED:** Yes, before handling real EU personal
  data — see `docs/SECURITY.md` §19. Not done, not started.

**Do not call this system production-ready as a whole.** Phase 4's own
scope is code-complete and logic-tested; the system as a whole still needs
Phases 5-10 and the infrastructure verification pass in §17.

## 19. Known issues

**Blocking (must resolve before this can run at all):**
- Nothing in the FastAPI/SQLAlchemy layer has been executed. The very
  first thing to do in an environment with normal network access is
  `pip install -r requirements.txt` and see what breaks.

**Non-blocking (should fix, don't have to before proceeding to Phase 5):**
- `customers.email` migration/model uniqueness mismatch (§5, §14).
- Email verification tokens are modeled but unused — `email_verified`
  stays `False` forever right now; no route issues/consumes one.
- `SessionService.validate_session()`'s `last_used_at` touch is not
  committed on pure-read requests (documented, deliberate trade-off — see
  the docstring in `session_service.py`).

**Future enhancement (not a defect):**
- `FixedWindowRateLimiter` is a fixed-window counter, a little bursty at
  window boundaries versus a sliding-window log — noted as an acceptable
  simplification in `docs/SECURITY.md` §8.
- No breach-corpus (e.g. HaveIBeenPwned k-anonymity) check in
  `password_policy.py` — needs outbound network access this sandbox
  couldn't make or verify anyway.

**External dependency (can't be resolved from inside this repo):**
- Everything in §12's "not yet integrated" column.

## 20. Do not casually reverse these decisions

- Vapi remains an interface/channel, never the business-logic owner. Tool
  handlers call into the existing service layer; they do not reimplement
  booking logic.
- Booking logic stays in application services (`app/services/*.py`), not
  in route handlers or (eventually) tool handlers.
- Airline integrations stay behind `AirlineProvider` — never call
  Amadeus/Sabre directly from a route or service.
- Customer ownership is enforced **server-side**, in
  `app/core/security/ownership.py`, and nowhere else duplicates this
  logic. See §7.
- Client-supplied identity headers (`x-user-id`, `customerId`, etc.) never
  become trusted identity, ever, for any reason, including "just for this
  one admin tool" or "just for testing."
- A PNR alone is never sufficient authorization for a mutation — see §8's
  verification requirement. Do not let a "just this once" exception creep
  in for a new endpoint.
- Money uses `Decimal`/`NUMERIC` (Phase 1-3 decision, still true) — never
  `float` for any fare/fee/payment amount.
- Database timestamps stay UTC.
- Sensitive credentials stay outside source control — `.env` is
  gitignored; `.env.example` gets placeholders only, forever.
- Mock providers (`MockAirlineProvider`, `MockEmailProvider`) stay
  deterministic — no `random`/wall-clock-dependent behavior that would
  make a test flaky.
- Idempotency stays enforced for every financial/booking mutation.
- `CurrentActor` is the only object authorization decisions are made
  from, and it is only ever constructed in `app/api/deps_auth.py` (or
  directly, in tests). Do not add a second code path that builds one.
- The `AuthError` exception (derives its HTTP status from
  `AuthErrorCode` automatically) is the pattern for new Phase 4/5 error
  codes — don't reintroduce the class-per-status mismatch described in
  §5's bug list by using `UnauthorizedError`/`ForbiddenError`/etc.
  directly for a new `AuthErrorCode`.

## 21. Next AI instruction

**Read this entire handoff before modifying the repository.** Then:

1. Inspect the repository yourself — don't take any claim in this
   document on faith where you can check it directly (run
   `python3 -m unittest tests.test_core_logic tests.test_security_core -v`
   yourself first; it should be 123/123 in under a second, no installs).
2. Verify this handoff against the actual files — if something here says
   a file was "extended" or "new," confirm that's still true; time may
   have passed, or a human may have made changes outside this process.
3. Run every test this environment allows before writing new code, and
   again before declaring anything done.
4. Do not assume undocumented functionality exists. If it's not in §3's
   "what is implemented" list or visible in the code, it isn't there.
5. Continue from **Phase 5 — Vapi voice agent** (§10/§11), unless
   explicitly told otherwise.
6. Do not rebuild Phases 1-4. They are code-complete for their own scope;
   extend, don't replace.
7. Only modify Phase 1-4 files when necessary to support Phase 5 or to
   fix a verified bug — and if you do, update this handoff document and
   `docs/PRODUCTION_CHECKLIST.md` to match, the same way this phase
   updated them for Phase 1-3's artifacts.

## 22. Changelog

**Phase 1 — Repository & infrastructure scaffold.** Monorepo layout,
Docker Compose config, FastAPI/Next.js skeletons, environment
configuration with fail-fast production validation. Tested: syntax-checked
only at the time; infrastructure never run in-sandbox (unchanged
limitation through Phase 4).

**Phase 2 — Database schema & mock provider.** 7-table Postgres/SQLite
schema, hand-written Alembic migration, `AirlineProvider` interface +
`MockAirlineProvider`. Tested: dependency-free core logic actually
executed; caught a flight-ID parser bug (broke on ISO-date hyphens) and an
unrealistic flight-duration formula (fixed with haversine). Decision:
placeholder Amadeus/Sabre adapters fail loudly rather than fabricate
responses — a principle Phase 4 followed again for password hashing (§5,
bug 3's "fail loudly, don't fabricate" reasoning) and Vapi actor
permissions (§9).

**Phase 3 — Core booking flows.** Search, quote, book, lookup, modify,
cancel, passenger management; idempotency; audit logging; passport
encryption. Tested: 30/30 dependency-free tests, real execution.

**Phase 4 — Authentication, RBAC & security hardening (this phase).**
Full auth/session/RBAC/ownership/verification/rate-limiting/CSRF/
redaction stack, architecturally-prepared Vapi security model, admin
bootstrap, frontend auth foundation. Tested: 93 new dependency-free tests,
real execution, alongside the original 30 (123 total). Important
decisions: `User`/`Customer` kept separate (§6); ownership authorization
centralized in one pure module (§7); booking verification is a real
stateful, scoped, rate-limited flow, not a per-request one-shot check
(§8); Vapi gets a distinct actor type whose permission set can never
include staff/admin permissions, by construction (§9); Argon2id via
`cryptography`'s native KDF instead of `argon2-cffi` specifically because
it let password hashing be *actually tested* in this sandbox instead of
just written (§4, §5 bug 3). Bugs found: a real IDOR hole, a mutable-state
aliasing bug, a dependency-pin bug that would have broken password hashing
entirely, and a minor password-policy check bug — all four found by
execution, all four fixed, all four documented in §5 in enough detail that
the *class* of mistake (not just the specific line) should be avoidable
going forward.
