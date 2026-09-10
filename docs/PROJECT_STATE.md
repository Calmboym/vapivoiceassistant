# Charter123 — Project State

**Status: CANONICAL, current as of 2026-09-09 (T-4 session).** This is a
terse, subsystem-by-subsystem snapshot for fast lookup. For narrative,
phase history, and contradictions, see `docs/PROJECT_ROADMAP.md` — that
file is authoritative if this one ever drifts from it.

Update this file whenever a meaningful implementation change lands.
Don't let it go stale the way `docs/ARCHITECTURE.md`/`README.md` did
before this audit (see `docs/PROJECT_ROADMAP.md` §6.2).

## How to read this file

Each row: what exists → what's verified → what isn't.
**Verified** = actually executed in a sandbox, with a test count.
**Written** = code exists, reviewed, compiles, but has never run.

## Infrastructure

| Component | State | Verified | Not verified |
|---|---|---|---|
| Monorepo scaffold | Written | `py_compile` clean on all 114 backend `.py` files (re-confirmed this audit) | Never run as a whole |
| Docker Compose (postgres, redis, mailhog, api, web) | Written | Config reviewed, standard images | Never run — no Docker in any sandbox to date |
| FastAPI app (`app/main.py`) | Written | Imports/wiring reviewed | Never imported — no `fastapi` installable here |
| Next.js app | Written | One status page + auth pages | Never run — no `npm install` possible here |
| PostgreSQL / migrations `0001`–`0004` | Written | Column-checked against models by hand (re-verified this audit for `0004`; `0001`'s `customers.email` claim corrected — see roadmap §6.3) | Never run against real Postgres |
| Redis | Written (in-process fallback exists) | Fallback used in all tests | Real Redis never exercised |

## Domain: flights, aircraft, airports (MockAirlineProvider)

| Component | State | Verified |
|---|---|---|
| `AirlineProvider` abstract interface | Complete | N/A (interface) |
| `MockAirlineProvider` | Complete | ✅ `tests/test_core_logic.py`, re-run this audit, passing |
| Flight search, fare quote (15-min expiry), haversine pricing, tiered cancellation fees | Complete | ✅ same suite |
| `AmadeusAirlineProvider` / `SabreAirlineProvider` | Placeholder by design (raises `NotImplementedError`) | N/A — compliant with spec §5/§40, not a gap |
| Airport reference data (18 airports incl. all spec §8 minimums) + "any London airport" group | Complete | ✅ seeded, matches spec example verbatim |
| Aircraft reference data | Complete | ✅ seeded |
| Dedicated `get_airport`/`search_airports` tool or route | **Missing** | New finding, this audit — no caller-facing way to query airport data at all today |

## Domain: bookings & passengers

| Component | State | Verified |
|---|---|---|
| `Booking`/`BookingPassenger` models, PNR generation | Complete | ✅ |
| Create / lookup / modify / cancel booking | Complete | ✅ (provider+service level); HTTP route written, not executed |
| Passenger add/remove | Complete | ✅ |
| Passenger update-in-place (`update_passenger`) | **Missing as a Vapi tool** — REST-layer support not confirmed this pass | New finding, this audit |
| Passport encryption (Fernet) + masked read-back | Complete | 🟡 written, not executed (needs `cryptography`+`pydantic` settings) |
| Idempotency (app-level `IdempotencyStore` + provider-level dedup) | Complete | ✅ |
| Identity verification for lookup/mutation (`BookingVerificationService`) | Complete | ✅ state machine; DB-backed service written, not executed |

## Auth, RBAC, security (Phase 4)

| Component | State | Verified |
|---|---|---|
| `User` model, Argon2id hashing, session auth (register/login/logout/refresh/reset) | Complete | ✅ password hashing + token logic; HTTP routes written, not executed |
| RBAC — 7 roles × **26** permissions (not 25 — see roadmap §6.5) | Complete | ✅ `RbacTests` |
| IDOR/ownership (`authorize_resource_access`) | Complete | ✅ `CriticalSecurityTest` (this is the function a real bug was found and fixed in — see `PROJECT_HANDOFF_PHASE_4.md` §5) |
| CSRF | Complete | ✅ token logic; middleware enforcement written, not executed |
| Rate limiting + progressive lockout | Complete | ✅ algorithm; Redis-backed adapter written, not executed |
| Security headers middleware | Written | Not executed |
| Log redaction | Complete | ✅ |
| Secret management (env-var only, `.env` gitignored) | Complete | ✅ audited |
| Audit logging | Written | Not executed against a real DB |
| Frontend auth pages + `AuthContext` + route-guard middleware (explicitly non-authoritative) | Written | Never run (`npm install` unavailable) |

## Vapi voice layer (Phase 5, and most of Phase 6's logic)

| Component | State | Verified |
|---|---|---|
| Webhook shared-secret auth | Complete | ✅ `WebhookAuthTests` |
| Tool JSON-schema registry (21 tools) | Complete | ✅ consistency-checked against the authorization matrix |
| `TOOL_AUTHORIZATION_MATRIX` (23 entries) | Complete | ✅ `VapiAuthorizationTests`/`ToolRegistryConsistencyTests` |
| Argument mapping + server-derived idempotency keys | Complete | ✅ |
| Dispatch table (16 of 21 tools wired to real services) | Complete for those 16 | ✅ |
| `Call`/`ToolExecution` models + migration `0003` | Written | Not executed |
| Rate limiting (webhook + per-call) | Complete | ✅ keying + algorithm; source-IP meaningfulness behind a proxy unverified |
| `transfer_to_human` (logs escalation; does not itself move the call) | Complete, correctly scoped | ✅ logic; native `transferCall` companion tool never configured in a real Vapi dashboard — `scripts/setup_vapi.py` (T-4) would now do this, but has never been run |
| `scripts/setup_vapi.py` (spec §51, T-4, 2026-09-09) | Written | ✅ 24 dependency-free tests (`scripts/test_setup_vapi.py`, all pure payload/planning logic + the system-prompt loader) + a real CLI dry-run exercised this session; networked half (`VapiClient`, the `--apply` path) never executed — needs `httpx` (not installed here) + network + a real `VAPI_API_KEY` |
| Live phone number / real inbound call | **Never done** | Blocked — needs a real Vapi account (see `docs/TASK_BOARD.md` T-4) |
| Multilingual (German/Persian) prompt/config | **Not started** | Explicitly documented as such in `docs/VAPI.md` |
| Tools registered but intentionally unavailable (5): `add_baggage`, `get_seat_options`, `select_seat`, `create_support_ticket`, `create_callback_request` | Registered as `implemented=False` placeholders | Genuine domain gaps, re-verified this audit by grepping for backing models — none exist |
| Tools from spec §19 **not registered at all** (8): `update_passenger`, `get_customer`, `create_customer`, `update_customer`, `end_call`, `get_airport`, `search_airports`, `get_faq` | **Missing entirely** | New finding, this audit — see `docs/PROJECT_ROADMAP.md` §6.4 |

## Payments (Phase 7, delivered under the repo's internal "Phase 6 Milestone 1" label — see roadmap §6.1; `refund_payment` added in T-3)

| Component | State | Verified |
|---|---|---|
| `Payment` model + state machine (5 states) | Complete — deliberately unmodified by T-3, see next row | ✅ `StateMachineTests` |
| `Payment` refund-tracking columns (`provider_refund_id`/`refunded_amount`/`refund_status`/`refunded_at`/`refund_reason`, migration `0005`) | Complete | Written, reviewed — needs a real Postgres to execute the migration |
| `PaymentProvider` abstraction + `MockPaymentProvider`, incl. `refund_payment` (T-3) | Complete | ✅ full lifecycle test incl. webhook parse; ✅ 8 new refund tests (full/partial/idempotent-replay/over-refund/unpaid/unknown-intent) |
| `StripePaymentProvider`, incl. `refund_payment` (T-3) | Written, cross-checked against live Stripe docs | Never executed — no network access in any sandbox to date, re-confirmed this session |
| `PaymentService` (shared by web + Vapi), incl. `apply_refund_outcome`/`refund_payment` (T-3) | Written | Not executed (needs FastAPI/SQLAlchemy) |
| Web routes (`/payments/sessions`, `/payments/status/{pnr}`, `/payments/refunds` (T-3), Stripe webhook receiver) | Written | Not executed |
| Vapi tools `create_payment_session`/`get_payment_status` | Complete | ✅ argument mapping/confirmation-gating/no-LLM-amount tests |
| `refund_payment` | **Complete (T-3)** — staff/admin-only REST route, NOT a Vapi tool by design (`STAFF_OR_ADMIN_ONLY` always denies `VAPI_AGENT`) | Written, reviewed; ✅ `test_authorization_entries_without_a_schema_are_exactly_staff_only` re-confirmed it correctly stays schema-less |
| Payment-link delivery (email/SMS) | **Not built** | Deliberately deferred — see Phase 8, and `docs/PAYMENTS.md` §8's explicit instruction not to close this quietly |
| Cancellation → real refund | **Complete (T-3)** — `CancellationService.cancel()` now calls `PaymentProvider.refund_payment()` for a `PAID` booking, using the airline's fee-adjusted `refundable_amount`; a provider failure leaves `payment_status="PAID"` (not falsely `"REFUNDED"`) and is recorded for manual staff follow-up via the new refund route | Written, reviewed — needs FastAPI/SQLAlchemy to execute; see `docs/PAYMENTS.md` §9 |
| Refund-status-change webhook (Stripe `refund.updated`/`charge.refunded`) | **Not built** | Deliberately out of T-3's scope — a `pending`/`requires_action` refund result is recorded honestly but nothing resolves it later on its own; see `docs/PAYMENTS.md` §9's last bullet and §13 |

## Notifications (Phase 8)

| Component | State |
|---|---|
| Email | `MockEmailProvider` only — **not a real delivery mechanism** |
| SMS | **Does not exist at all** |

## Admin dashboard (Phase 9)

| Component | State |
|---|---|
| `/api/v1/admin`, `/api/v1/customers`, `/api/v1/calls` routes | **Do not exist** |
| Admin UI pages | **Do not exist** |
| Backing authorization (RBAC roles/permissions) | Exists and tested — the boundary is ready, nothing uses it yet |

## Testing (Phase 10)

| Suite | Count | State |
|---|---|---|
| `tests/test_core_logic.py` | 30 | ✅ passing |
| `tests/test_security_core.py` | 93 | ✅ passing |
| `tests/test_vapi_core.py` | 56 | ✅ passing |
| `tests/test_payments_core.py` | 46 (33 + 13 new for T-3's `refund_payment`) | ✅ passing |
| **Total dependency-free** | **236 pass** | ✅ **re-executed and confirmed this session** (`python3 -m unittest tests.test_core_logic tests.test_security_core tests.test_vapi_core tests.test_payments_core tests.test_api_security tests.test_vapi_api -v` → `OK (skipped=8)`) |
| `tests/test_api_security.py` | 18 methods, 6 classes | Written against real `TestClient`; skips cleanly here (no FastAPI) |
| `tests/test_vapi_api.py` | 2 classes | Written; skips cleanly here |
| `tests/{e2e,integration,voice}/` | 0 | Placeholders only — `README.md` in each, no test code |
| `scripts/test_setup_vapi.py` (T-4, separate suite — repo-root `scripts/`, not `apps/api/tests/`; NOT part of the 236 above or `.github/workflows/t1-verify.yml`'s pinned baseline) | 24 | ✅ passing (`cd scripts && python3 -m unittest test_setup_vapi -v` → `OK`) |

## Known residual security/integrity findings (this audit — see roadmap §6.6 for detail)

- Direct REST booking routes trust an unauthenticated `x-charter123-call-id`
  header for audit-log attribution only (no privilege impact, but a real
  audit-trail integrity gap).
- Vapi webhook rate-limit numbers are unvalidated placeholders.
- Concurrent (not sequential) double-delivery of the same
  `vapi_tool_call_id` is mitigated, not eliminated.
- `InMemoryIdempotencyStore` and in-process Redis/rate-limit fallbacks are
  single-process only.
