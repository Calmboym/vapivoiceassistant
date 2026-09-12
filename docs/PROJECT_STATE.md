# Charter123 — Project State

**Status: CANONICAL, current as of 2026-09-11 (T-6 session).** This is a
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
| Monorepo scaffold | Written | `py_compile` clean on all 131 `app/**/*.py` files (re-confirmed this session, up from 119 pre-T-6 — 12 new admin-dashboard modules; 140 total across `apps/api` including `tests/`) | Never run as a whole |
| Docker Compose (postgres, redis, mailhog, api, web) | Written | Config reviewed, standard images | Never run — no Docker in any sandbox to date |
| FastAPI app (`app/main.py`) | Written | Imports/wiring reviewed | Never imported — no `fastapi` installable here |
| Next.js app | Written | 21 `.ts`/`.tsx` files (up from 14 pre-T-6 — the new `/admin` section, its first `components/` directory, and `lib/adminTypes.ts`); syntax-checked via a standalone `tsc --noResolve` pass this session (see `docs/TASK_BOARD.md` T-6's "Testing status" for exactly what that proves and doesn't) | Never run — no `npm install` possible here |
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
| `/login`'s `next=` redirect (T-7, 2026-09-12) | **Fixed** — was silently ignored, always landing on `/account` even when `admin/layout.tsx` sent a staff member here via `/login?next=/admin`; found while writing `tests/e2e/admin/`'s login test | Syntax-checked via standalone `tsc` (no real errors, only expected missing-module noise — no `node_modules` installed); regression-tested by `tests/e2e/admin/tests/auth-gate.spec.ts` (written, never executed, same as the rest of that suite) |

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
| Payment-link delivery (email/SMS) | **Complete (T-5)** — see Phase 8 below; `docs/PAYMENTS.md` §8's earlier "needs its own milestone with its own review" instruction was honored, not bypassed | Written, reviewed, cross-checked against live Resend/Twilio docs; content-builder logic executed (31 tests); provider HTTP calls themselves NOT executed — no network access |
| Cancellation → real refund | **Complete (T-3)** — `CancellationService.cancel()` now calls `PaymentProvider.refund_payment()` for a `PAID` booking, using the airline's fee-adjusted `refundable_amount`; a provider failure leaves `payment_status="PAID"` (not falsely `"REFUNDED"`) and is recorded for manual staff follow-up via the new refund route | Written, reviewed — needs FastAPI/SQLAlchemy to execute; see `docs/PAYMENTS.md` §9 |
| Refund-status-change webhook (Stripe `refund.updated`/`charge.refunded`) | **Not built** | Deliberately out of T-3's scope — a `pending`/`requires_action` refund result is recorded honestly but nothing resolves it later on its own; see `docs/PAYMENTS.md` §9's last bullet and §13 |

## Notifications (Phase 8 — T-5, 2026-09-09)

| Component | State | Verified |
|---|---|---|
| `EmailProvider` interface | Extended (2 original methods unchanged; 2 new: `send_booking_confirmation`/`send_payment_link`) | ✅ `MockEmailProvider` — see Testing below |
| Email — real provider | `ResendEmailProvider` (`app/services/email_provider.py`), selected via `EMAIL_PROVIDER=resend` | Written, cross-checked against live Resend API docs — never executed, no network access |
| `SmsProvider` interface | New — one method, `send_payment_link` (booking confirmation stays email-only by design; see `docs/TASK_BOARD.md` T-5's "Decisions/deviations") | ✅ `MockSmsProvider` — see Testing below |
| SMS — real provider | `TwilioSmsProvider` (`app/services/sms_provider.py`), selected via `SMS_PROVIDER=twilio` | Written, cross-checked against live Twilio API docs — never executed, no network access |
| `NotificationService` (dispatch/audit orchestration) | Complete — best-effort, non-blocking by design; never a Vapi tool (MASTER_RULES §6) | Written, reviewed — needs SQLAlchemy to execute |
| Content builders (`app/core/notifications/content.py`) | Complete — stdlib-only on purpose | ✅ 31 tests, `tests/test_notifications_core.py` |
| Booking-confirmation wiring (`BookingService.create_booking`) | Complete — email only | Written, reviewed — needs SQLAlchemy to execute |
| Payment-link wiring (`PaymentService.create_payment_session`) | Complete — email always, SMS when `call_id is not None` | Written, reviewed — needs SQLAlchemy to execute |
| Known honest gap | Baggage allowance defaults to `CabinClass.ECONOMY` (Booking doesn't persist cabin class); cancellation-terms line is always generic (`Booking.cancellation_deadline` is never populated anywhere in this codebase — pre-existing, found not fixed) | Documented in `content.py`'s docstring, not silently assumed correct |
| Audit-log PII fix (T-7, WBS-6.3 security pass, 2026-09-12) | **Fixed** — the three delivery-failure audit calls in `notification_service.py` used to store the provider's raw `message` string alongside `error_code`; Twilio's (21211/21614) and Resend's own documented error formats echo the rejected phone number/email back inside that text, and T-6's new admin audit-trail endpoint renders `event_metadata` verbatim — so a delivery failure could leak a customer's own contact details into a log surface. `error_message` dropped from all three call sites; `error_code` (a bounded, provider-defined value) kept | Reviewed by inspection, matches this codebase's existing `arguments_redacted`/"field names only" audit-redaction pattern elsewhere; not independently unit-tested — needs SQLAlchemy, same as the rest of this file |

## Admin dashboard (Phase 9 — T-6, 2026-09-11)

| Component | State | Verified |
|---|---|---|
| `/api/v1/customers` (list/get/patch), `/api/v1/calls` (list/get), `/api/v1/admin/{bookings,bookings/{id},analytics}` | **Complete** | Written, reviewed — needs FastAPI/SQLAlchemy to execute |
| `authorize_staff_access()` / `require_staff_permission()` (new authorization primitive — customers-list needs it, admin/calls routes don't, see `docs/TASK_BOARD.md` T-6) | Complete | ✅ `tests/test_security_core.py::StaffAccessTests` (8 tests) + `RbacTests::test_customer_role_never_holds_admin_or_calls_permissions` |
| `app/core/admin/analytics.py` (pure rate/revenue calculations — stdlib-only, same discipline as T-5's `content.py`) | Complete | ✅ 13 tests, `tests/test_admin_core.py` |
| `AuditLogRepository` — this table's first reader (writer existed since Phase 4) | Complete | Written, reviewed — needs SQLAlchemy to execute |
| Admin UI pages (`apps/web/app/admin/**` — overview/bookings/customers/calls, 7 pages + layout gate) | Complete | Written; syntax-checked via standalone `tsc --noResolve` (zero `TS1xxx`), NOT type-checked against a real toolchain — see `docs/TASK_BOARD.md` T-6's "Testing status" for exactly what that does and doesn't prove |
| Known honest gap (analytics) | No "quote conversion rate" metric — not computable from what's persisted today (`"QUOTE"` is declared in `BOOKING_STATUSES` but never actually written to a stored `Booking.status` by any code path; confirmed by grep) | Documented in `analytics.py`'s module docstring, not silently assumed |
| Pre-existing inconsistency found, not fixed | `AuditLog.resource_id` for `resource="booking"` events is `pnr`-keyed at every current write site (`booking_service.py`/`cancellation_service.py`/`passenger_service.py`) — the admin booking-detail route defensively queries both `pnr` and `str(booking.id)` and merges, but the underlying inconsistency-risk (an unconstrained `String` column) is not structurally fixed | `docs/TASK_BOARD.md` T-6, "Decisions/deviations" #3 |

## Testing & hardening (Phase 10 — T-7, 2026-09-12)

WBS-6.1/6.2/6.3 (docs/TASK_BOARD.md's T-7; WBS-6.4/6.5/6.6 remain separate
— see T-8/PROPOSED entries). Three deliverables:

1. **Playwright E2E, admin half only** (`tests/e2e/admin/`) — a real,
   written suite against the actual admin dashboard component source
   (Phase 9/T-6): dashboard, bookings/customers/calls list + detail,
   login redirect gate. WRITTEN, NEVER EXECUTED (no Node network access
   in this sandbox; no live stack to point it at regardless). Found and
   fixed one real bug while writing it (`/login`'s `next=` param, see
   Auth section above). The customer-facing half (search → book → lookup
   → cancel → modify → human transfer) has no pages to test against —
   `apps/web/app/` still only has `account/`, `admin/`, `login/`,
   `register/`, and a status `page.tsx` — so it was NOT built here rather
   than fabricating a UI; see `tests/e2e/README.md` and the T-7 handoff
   for the open sequencing question this leaves for the owner.
2. **Voice conversation test suite** (`apps/api/tests/test_voice_
   conversation_core.py`, WBS-6.2) — 29 dependency-free tests, one class
   per spec-§56 scenario the WBS names (6, not the 7 it claims — see that
   file's own docstring on the count mismatch, reproduced honestly rather
   than resolved by inventing a 7th case). Tests the actual backend
   guarantee behind each scenario (argument-mapping/authorization/
   provider code), not live LLM conversational behavior — that half still
   needs WBS-2.2-2.5's live phone number, which remains BLOCKED.
3. **Security-testing pass** (WBS-6.3) — `PROJECT_HANDOFF_PHASE_5.md`
   §11's checklist repeated against everything T-3/T-4/T-5/T-6 added.
   Two real findings, both fixed (see Auth and Notifications sections
   above for detail): `app/core/encryption.py`'s `mask_for_speech` was
   unimportable without pydantic+structlog (now lazy-imported, fixed);
   `notification_service.py`'s failure-audit metadata could leak a
   customer's own phone/email via the provider's error text (now
   dropped). No new authn/authz/SSRF/webhook-spoofing/injection findings
   in T-3/T-4/T-5/T-6's own new code — see the T-7 handoff
   (`docs/handoffs/2026-09-12-t7-testing-hardening.md`) for the full
   checklist-by-checklist writeup, including what was reviewed and found
   clean, not just what was fixed.

| Suite | Count | State |
|---|---|---|
| `tests/test_core_logic.py` | 30 | ✅ passing |
| `tests/test_security_core.py` | 104 (95 + 9 for T-6's `StaffAccessTests`/RBAC additions) | ✅ passing |
| `tests/test_vapi_core.py` | 65 | ✅ passing |
| `tests/test_payments_core.py` | 46 (33 + 13 for T-3's `refund_payment`) | ✅ passing |
| `tests/test_notifications_core.py` | 31 | ✅ passing |
| `tests/test_admin_core.py` (T-6) | 13 | ✅ passing |
| `tests/test_voice_conversation_core.py` (T-7, new) | 29 | ✅ passing |
| **Total dependency-free** | **318 pass** | ✅ **re-executed and confirmed this session** (`python3 -m unittest tests.test_core_logic tests.test_security_core tests.test_vapi_core tests.test_payments_core tests.test_notifications_core tests.test_admin_core tests.test_voice_conversation_core -v` → `OK`; `tests.test_api_security tests.test_vapi_api` re-run separately → skip cleanly, `skipped=8`, unchanged) |
| `tests/test_api_security.py` | 18 methods, 6 classes | Written against real `TestClient`; skips cleanly here (no FastAPI) |
| `tests/test_vapi_api.py` | 2 classes | Written; skips cleanly here |
| `tests/e2e/admin/` (T-7, new) | 3 spec files, 11 tests | Written, never executed — see item 1 above |
| `tests/e2e/` (customer-facing flow) | 0 | Not started — no pages exist to test against; see item 1 above |
| `tests/integration/` | 0 | Placeholder only — `README.md`, no test code |
| `scripts/test_setup_vapi.py` (T-4, separate suite — repo-root `scripts/`, not `apps/api/tests/`; NOT part of the 318 above or `.github/workflows/t1-verify.yml`'s pinned baseline) | 24 | ✅ passing (`cd scripts && python3 -m unittest test_setup_vapi -v` → `OK`) |

## Known residual security/integrity findings (this audit — see roadmap §6.6 for detail)

- Direct REST booking routes trust an unauthenticated `x-charter123-call-id`
  header for audit-log attribution only (no privilege impact, but a real
  audit-trail integrity gap).
- Vapi webhook rate-limit numbers are unvalidated placeholders.
- Concurrent (not sequential) double-delivery of the same
  `vapi_tool_call_id` is mitigated, not eliminated.
- `InMemoryIdempotencyStore` and in-process Redis/rate-limit fallbacks are
  single-process only.
- (T-7, found not fixed — narrower/lower-confidence sibling of the
  Notifications-section fix above, deliberately left alone rather than
  over-generalizing a fix across a different provider family without
  owner sign-off) `cancellation_service.py`'s `payment.refund_failed_
  during_cancellation` audit entry still stores a raw `str(exc)` from
  `PaymentProviderError` (Stripe) in `event_metadata` — Stripe's error
  shapes are less likely to echo request PII than Twilio/Resend's, but
  this wasn't independently confirmed against live Stripe error text.
- (T-7) T-6's new admin routes (`/api/v1/customers`, `/api/v1/calls`,
  `/api/v1/admin/*`) carry no rate limiting, unlike the public-facing
  `bookings.py`/`auth.py`/Vapi webhook surfaces that do
  (`app/core/security/rate_limiter.py`). Reviewed and not flagged as a
  gap requiring a fix: every admin route already requires staff
  authentication + a specific RBAC permission, a materially smaller and
  more accountable population than the public unauthenticated surfaces
  rate limiting protects elsewhere in this codebase. Recorded here in
  case the project's threat model later wants to cover
  compromised-staff-credential bulk scraping, which this does not.
