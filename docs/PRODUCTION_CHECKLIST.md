# Production Checklist

Status against the original spec's §79 "Definition of Done," checked
honestly rather than optimistically. This file tracks line-item
verification status only. **It is not the roadmap** — for phase
narrative, sequencing, contradictions, and what to do next, see
`docs/PROJECT_ROADMAP.md`, which is canonical if this file ever
disagrees with it.

> **2026-09-07 audit note:** items 16–25 below and the "Explicitly out of
> scope" section were stale — they described Vapi as not started, when
> Phase 5 was in fact complete. Fixed in this pass. See
> `docs/PROJECT_ROADMAP.md` §6.2 for how that happened and §6.3 for a
> previously-recorded item in this file (the `customers.email` note) that
> turned out, on direct inspection, not to be a real defect — also fixed
> below, at the bottom of this file.

Legend: ✅ done & verified in this sandbox · 🟡 written, not yet verified
(needs packages/services this sandbox doesn't have) · ⬜ not started.

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | `docker compose up --build` works | 🟡 | Files are written and internally consistent; never actually run — no Docker access in any sandbox used on this project to date, this audit's included. **Run this first in your environment and report back anything that breaks.** |
| 2 | PostgreSQL starts | 🟡 | Compose config is standard `postgres:16-alpine`; not run here. |
| 3 | Redis starts | 🟡 | Compose config is standard `redis:7-alpine`; app also runs without it (in-process fallback). |
| 4 | FastAPI starts | 🟡 | Every `app/**/*.py` file passes `python3 -m py_compile` (no syntax errors — re-confirmed this session, all 119 files, up from 114 before T-5's 4 new files: `content.py`, its package `__init__.py`, `sms_provider.py`, `notification_service.py`), and the dependency-free half imports and runs correctly. The FastAPI/SQLAlchemy half has never actually been imported — `pip install` is required first. |
| 5 | Next.js starts | 🟡 | Never run — no `npm install` possible here (registry blocked). |
| 6 | Migrations run | 🟡 | Hand-written (no `alembic` installed to autogenerate/run it), checked column-by-column against the actual model files — 0001 through 0004, re-checked this audit. |
| 7 | Seed data loads | 🟡 | `app/db/seed.py` written, not run. Reference data (18 airports incl. all spec §8 minimums, London disambiguation group, aircraft) confirmed present in `app/providers/airline/reference_data.py` by direct inspection. |
| 8 | Flight search works | ✅ | Verified: `tests/test_core_logic.py::MockProviderSearchTests` (5 tests). |
| 9 | Fare quote works | ✅ | Verified: `test_quote_total_equals_base_plus_tax_plus_fee`. |
| 10 | Booking creation works | ✅ | Verified at the provider/logic level (`BookingLifecycleTests`). The HTTP route (`POST /api/v1/bookings`) is written but not executed. |
| 11 | Booking lookup works | ✅ / 🟡 | Provider-level `get_booking` verified. `BookingVerificationService`'s email/phone/last-name check has no dedicated unit test yet. |
| 12 | Cancellation works | ✅ | Verified, including idempotent double-cancel and fee-tier escalation near departure. **Fixed in T-3**: the refund-amount calculation was already verified; the `payment_status → REFUNDED` transition now calls the real `PaymentProvider` for a paid booking (net of the cancellation fee) instead of only flipping the local field — see item 60 below and `docs/PAYMENTS.md` §9. |
| 13 | Modification works | ✅ | Verified: `test_update_booking_rebooks_to_a_new_flight_and_recomputes_price`, `test_update_booking_is_idempotent`, `test_cannot_modify_a_cancelled_booking`. |
| 14 | Passenger management works | ✅ | Verified: add/remove passenger recomputes price correctly; removing the last passenger is rejected. No `update_passenger` path exists yet (see item 57). |
| 15 | Stripe test flow works | 🟡 | `create_payment_session`/`get_payment_status`/`refund_payment` implemented (model, provider abstraction, service, web routes, Vapi tools) and the dependency-free portions (state machine, mock provider incl. refund, argument mapping, authorization) are ✅ verified — see `docs/PAYMENTS.md` §12 for the full per-component breakdown. `StripePaymentProvider` itself and everything requiring FastAPI/SQLAlchemy remain 🟡 unexecuted (no network access in any sandbox to date, this session's included) — a real Stripe test-mode Checkout Session or refund completing end-to-end has not been attempted. |
| 16 | Vapi webhook works | ✅ / 🟡 | **Phase 5, complete as code.** `POST /api/v1/vapi/webhook` — shared-secret auth, `end-of-call-report`/`tool-calls` event handling, `Call`/`ToolExecution` persistence. Auth logic + dispatch ✅ executed (`WebhookAuthTests` etc., part of the 267 below — see item 31). The FastAPI route itself is 🟡, same constraint as every HTTP route in this table. |
| 17 | Vapi tools work | ✅ / 🟡 | **Phase 5, complete.** 21 tool JSON schemas (`app/core/vapi/tool_schemas.py`), 23-entry authorization matrix, 16 wired to real dispatch functions, 5 correctly registered `implemented=False` placeholders for genuinely unbuilt domain features (seat selection, baggage add, support tickets, callback requests). Schema ⇄ matrix ⇄ dispatch consistency independently re-verified this audit. ✅ logic-level tests pass; HTTP execution 🟡. **This audit found 8 tools from the original spec §19 list not registered at all** (`update_passenger`, `get_customer`, `create_customer`, `update_customer`, `end_call`, `get_airport`, `search_airports`, `get_faq`) — see `docs/PROJECT_ROADMAP.md` §6.4, a new finding, not previously tracked here. |
| 18 | Vapi Assistant can call the backend | 🟡 | The webhook/tool layer that would receive such a call is ✅ complete and tested (item 16–17). Whether a real Vapi Assistant configuration actually calls it has never been tested — no live Vapi account has been used on this project. `scripts/setup_vapi.py` (spec §51), which would create/attach the Assistant, was never written. |
| 19 | Inbound phone call reaches the assistant | ⬜ | Not started — needs a live Vapi account + phone number + `scripts/setup_vapi.py`. This is the one piece of the original spec's Phase 6 that Phase 5's work did not already cover — see `docs/PROJECT_ROADMAP.md` §6.1. |
| 20–25 | AI can search/read/book/retrieve/cancel/transfer | ✅ (logic) / ⬜ (live) | The tool-dispatch logic for all six of these exists and is tested (search_flights, get_booking, create_booking, cancel_booking, modify_booking, transfer_to_human — item 17). None of the six has been exercised via an actual live voice call — that requires item 19 first. |
| 26 | Failed provider calls are handled gracefully | 🟡 | `ProviderError` → structured, customer-safe envelope exists (`app/core/exceptions.py`); not exercised against a real failure injection test. |
| 27 | Duplicate tool calls are idempotent | ✅ | Verified at the application-idempotency-store level, the provider level, and (Phase 5) the Vapi `ToolExecution`/`vapi_tool_call_id` level. |
| 28 | Sensitive information is redacted | ✅ / 🟡 | `app/core/security/redaction.py` — pure, recursive, depth-capped, plus a secret-value-pattern scan — ✅ real, executed (`RedactionTests`). Passport encryption/masking remains 🟡 — never executed, needs `pydantic`-based settings which aren't importable here either. |
| 29 | RBAC works | ✅ / 🟡 | Permission-resolution engine (`app/core/security/rbac.py`, **7 roles × 26 permissions** — corrected from an earlier "25," see `docs/PROJECT_ROADMAP.md` §6.5) and the IDOR-prevention core (`app/core/security/ownership.py`) are ✅ real, executed, passing. Wired into every booking/passenger/payment mutation route. HTTP-level wiring itself is 🟡. |
| 30 | Audit logs work | 🟡 | Never executed against a real DB. **Known integrity gap, found this audit**: the direct REST booking routes trust an unauthenticated `x-charter123-call-id` header to build the audit log's `actor` string — no privilege impact, but a real forgeable-attribution gap. See `docs/PROJECT_ROADMAP.md` §6.6. |
| 31 | Tests pass | ✅ / 🟡 | **267/267 dependency-free tests pass** — re-executed and confirmed 2026-09-09 (T-5): `cd apps/api && python3 -m unittest tests.test_core_logic tests.test_security_core tests.test_vapi_core tests.test_payments_core tests.test_api_security tests.test_vapi_api tests.test_notifications_core -v` → `OK (skipped=8)`. Breakdown: 30 (Phase 1-3) + 95 (Phase 4 security-core) + 65 (Phase 5 Vapi-core) + 46 (Phase 7, incl. T-3's `refund_payment`) + 31 (Phase 8/T-5 notifications, new) — corrected this session from a stale 223/93/56 carried in this row since the 2026-09-07 audit, which never actually summed to its own claimed total; re-counted by direct execution, not assumed. The 8 skips are `tests/test_api_security.py` (6 classes/18 methods) and `tests/test_vapi_api.py` (2 classes) — written against real FastAPI `TestClient`, correctly skip (not fail) with no network. |
| 32 | OpenAPI documentation works | 🟡 | FastAPI generates this automatically from route/schema code at `/docs`; never actually loaded (no FastAPI installed anywhere this project has been built). |
| 33 | README is complete | ✅ | See `/README.md` — corrected this audit for the same staleness described in the banner above. |
| 34 | Production configuration is documented | ✅ | `docs/ENVIRONMENT_VARIABLES.md` (corrected this audit — see banner above) + `Settings.validate_for_production()` fails fast on missing required config. |

## Phase 4 — Authentication, Authorization & Security

Legend as above. See `docs/SECURITY.md` for the architecture and
`PROJECT_HANDOFF_PHASE_4.md` for the full engineering handoff, including
every real bug found and fixed during this phase.

| # | Item | Status | Notes |
|---|---|---|---|
| 35 | User model / registration / login | ✅ / 🟡 | `POST /auth/register`, `/login` written and correct against the real API; Argon2id hashing itself (via `cryptography`'s native KDF, **not** `argon2-cffi`) is ✅ **actually executed**. The HTTP route layer around it is 🟡. |
| 36 | Sessions (create/validate/refresh/revoke) | ✅ / 🟡 | Token generation/hashing ✅ executed. `SessionService` (DB-backed) is 🟡, written, not executed. |
| 37 | Password reset architecture | ✅ / 🟡 | Token issuance/expiry/single-use logic ✅ executed. `AuthService.request_password_reset`/`reset_password` (DB-backed, `MockEmailProvider`) are 🟡. |
| 38 | RBAC permission matrix | ✅ | `app/core/security/rbac.py` — 7 roles × **26** permissions (corrected count, see item 29), real executed tests (`RbacTests`). |
| 39 | Customer ownership / IDOR prevention | ✅ | `app/core/security/ownership.py`. **A real IDOR bug was found and fixed here** — the staff-permission check ran before the ownership check. Caught by `CriticalSecurityTest` actually failing on first run. See `PROJECT_HANDOFF_PHASE_4.md` §5. |
| 40 | Booking verification (§12 state machine) | ✅ / 🟡 | State machine ✅ executed. `VerificationSessionService` (DB-backed) and `POST /bookings/{pnr}/verify` are 🟡. Closed a real gap: `cancel_booking`/`modify_booking` previously trusted only a client-supplied `customer_confirmed: bool` with no identity check. This same verification path was later reused, unmodified, by the Vapi and Payments layers — see `docs/SECURITY.md` §7/§22. |
| 41 | Vapi security preparation | ✅ | The authorization architecture built here (`VAPI_AGENT` actor type, tool-authorization matrix) turned out to be exactly what Phase 5 needed unchanged — `VapiAuthorizationTests` still passing, matrix grown from its Phase-4 size to 23 entries without restructuring. |
| 42 | Admin bootstrap | 🟡 | `app/db/bootstrap_admin.py` written, refuses to run unless `BOOTSTRAP_ADMIN_ENABLED=true` + both credentials set. Not executed (needs SQLAlchemy). |
| 43 | Rate limiting | ✅ / 🟡 | Algorithm ✅ executed against a fake in-memory store, including login/register/password-reset/booking-lookup/booking-verification/vapi-webhook/vapi-tool/admin-login profiles. The Redis-backed adapter is 🟡. |
| 44 | CSRF | ✅ / 🟡 | Token issue/verify (signed, session-bound double-submit) ✅ executed. The enforcing middleware is 🟡. |
| 45 | CORS | ✅ | Audited, not rewritten — Phase 1-3's config was already correct. |
| 46 | Security headers | 🟡 | Written; not executed. |
| 47 | Secret management | ✅ | Audited. **A real bug was found and fixed**: `requirements.txt` pinned `cryptography>=43.0,<44.0`, excluding every version with Argon2id support (added in 44.0.0). Fixed to `>=44.0,<47.0`. |
| 48 | Log redaction | ✅ | See item 28. |
| 49 | Frontend auth foundation | 🟡 | Login/register/account pages, `AuthContext`, a UX-only route guard. Never run — no `npm install` here. |
| 50 | Phase 1-3 regression check | ✅ | Re-run and re-confirmed green after every Phase 4 change, and again after Phase 5 and Phase 7 M1. |

## Phase 5 — Vapi Integration

See `docs/VAPI.md` for the full architecture and `PROJECT_HANDOFF_PHASE_5.md`
for the engineering handoff. **This section did not previously exist in
this file — added by the 2026-09-07 audit to close the staleness described
in the banner at the top.**

| # | Item | Status | Notes |
|---|---|---|---|
| 51 | Webhook shared-secret authentication | ✅ | `app/core/security/vapi_webhook_auth.py` — ✅ executed (`WebhookAuthTests`). |
| 52 | Tool schema registry (21 tools) + authorization matrix (23 entries) | ✅ | Internally consistent — re-verified this audit by direct grep, independent of the prior claim. See item 17 for the 8-tool gap this audit found relative to the original spec's §19 list. |
| 53 | Server-derived idempotency keys for voice-triggered mutations | ✅ | `derive_idempotency_key(call_id, operation, payload)` — never LLM-supplied. |
| 54 | `Call`/`ToolExecution` persistence | 🟡 | Models + migration `0003` written, column-checked, not executed against real Postgres. |
| 55 | `transfer_to_human` correctness | ✅ | Corrected during Phase 5 to log the escalation without claiming a live transfer occurred — only Vapi's native `transferCall` tool can actually move a call, and that has never been configured (see item 18/19). |

## Phase 7 Milestone 1 — Payments

See `docs/PAYMENTS.md` for the full architecture and
`docs/handoffs/2026-09-06-phase6-milestone1-payments.md` for the
engineering handoff. **Note the label mismatch**: that handoff and
`docs/PAYMENTS.md` call this "Phase 6 Milestone 1" — the original spec's
Phase 6 is telephony, not payments (which is Phase 7). See
`docs/PROJECT_ROADMAP.md` §6.1 for the full explanation; this section
uses the original spec's numbering, matching the rest of this file.
**This section did not previously exist in this file — added by the
2026-09-07 audit.**

| # | Item | Status | Notes |
|---|---|---|---|
| 56 | `Payment` model + 5-state state machine | ✅ | ✅ executed (`StateMachineTests`). |
| 57 | `PaymentProvider` abstraction + `MockPaymentProvider` | ✅ | ✅ executed, full lifecycle incl. webhook parsing. |
| 58 | `StripePaymentProvider` | 🟡 | Written, cross-checked against live Stripe API docs; never executed — no network access in any sandbox to date. |
| 59 | `create_payment_session`/`get_payment_status` Vapi tools | ✅ | ✅ executed — confirmation-gating, no-LLM-supplied-amount, argument mapping all tested. |
| 60 | `refund_payment` | 🟡 | **Implemented, T-3** — `PaymentProvider.refund_payment()` (both providers), `PaymentService.refund_payment`/`apply_refund_outcome`, staff-only `POST /api/v1/payments/refunds`, and `CancellationService.cancel()` wired to call it. Dependency-free portions (mock provider, error types) ✅ executed — 8 new refund tests. Everything needing FastAPI/SQLAlchemy/`stripe` is 🟡 written, unexecuted (same sandbox constraint as the rest of this table). |
| 61 | Payment-link delivery to a phone caller | 🟡 | **Implemented, T-5, 2026-09-09** — see Phase 8 section below for the full breakdown. No longer "not built" (⬜); email is sent for every session, SMS additionally for one created during a live voice call — this item's original scenario. Content-builder logic ✅ executed (31 tests); `ResendEmailProvider`/`TwilioSmsProvider` themselves are 🟡, unexecuted, same sandbox constraint as `StripePaymentProvider` above. |

## Phase 8 — Notifications

See `docs/PAYMENTS.md` §8 and `docs/TASK_BOARD.md`'s T-5 entry for the
full architecture and decision log. **This section did not previously
exist in this file — added 2026-09-09, T-5** (Phase 8 was previously
represented only by item 61 above, under Phase 7).

| # | Item | Status | Notes |
|---|---|---|---|
| 62 | `EmailProvider` real implementation (Resend) | 🟡 | `ResendEmailProvider` (`app/services/email_provider.py`) — written, cross-checked against Resend's live API reference fetched this session; never executed, no network access in any sandbox to date. Original interface's two methods unchanged; two new ones added (`send_booking_confirmation`/`send_payment_link`). |
| 63 | `SmsProvider` (new interface) + real implementation (Twilio) | 🟡 | `app/services/sms_provider.py` (new file) — `SmsProvider` Protocol + `MockSmsProvider` + `TwilioSmsProvider`, same execution caveat as item 62, cross-checked against Twilio's live API reference. |
| 64 | Booking-confirmation delivery (spec §44) | ✅ / 🟡 | Content-builder logic (PNR, passenger names, itinerary, price, payment status, honest cancellation/baggage handling, **never a passport number**) is ✅ executed — 31 tests, `tests/test_notifications_core.py`, including a structural test that `PassengerSummary` has no passport-shaped field at all. Wiring into `BookingService.create_booking` (`NotificationService`) is 🟡, needs SQLAlchemy. |
| 65 | Payment-link delivery (spec, `docs/PAYMENTS.md` §8) | ✅ / 🟡 | Same split as item 64 — content-builder ✅ executed (same 31 tests); wiring into `PaymentService.create_payment_session` is 🟡. Best-effort/non-blocking by design: a delivery failure is caught, audited, and never rolls back a payment session that already succeeded with Stripe. |
| 66 | A real email or SMS actually arriving | ⬜ | Not attempted — needs real `RESEND_API_KEY`/`TWILIO_*` credentials and network egress, neither of which any sandbox this project has used has ever had. |

## What this means practically

**Do this first, in an environment with normal network access:**
```bash
cp .env.example .env
docker compose up --build
```
Then work through the 🟡 rows top to bottom — each one is either "run it
and see" or "write the missing test." None of them are expected to be
hard; they just couldn't be executed inside any build sandbox used on
this project to date. See `docs/WORK_BREAKDOWN_STRUCTURE.md` WBS-1 for
the exact sequence.

## Explicitly out of scope in this delivery (not started at all)

Updated 2026-09-07 — Vapi implementation is no longer in this list (see
Phase 5 section above; it's done). Updated 2026-09-08 (T-3) —
`refund_payment` is no longer in this list either (see Phase 7 section
above; it's implemented, unexecuted pending T-1). Updated 2026-09-09
(T-4/T-5) — `scripts/setup_vapi.py` and email/SMS notifications are no
longer in this list either (see items 18/19 and the Phase 8 section
above; both written, unexecuted pending live accounts + network access).
Remaining, from the
original spec: callback requests
(§45), the FAQ/knowledge base (§46), private charter quoting (§47–48),
the admin dashboard (§32–34 — the backend authorization boundary exists;
no routes or UI do), i18n (§41), GDPR export/deletion endpoints (§66),
call recording/transcription (§21–22, 67), the Playwright/E2E/voice test
suites (§55–56).

**New, from this audit**, not previously tracked anywhere: 8 tools from
spec §19 with no registration at all (`update_passenger`, `get_customer`,
`create_customer`, `update_customer`, `end_call`, `get_airport`,
`search_airports`, `get_faq` — see item 17); the audit-log actor-
attribution gap on direct REST routes (see item 30).

These follow the build order in `docs/PROJECT_ROADMAP.md` §7 — see that
file for the recommended sequence and `docs/TASK_BOARD.md` for what's
currently authorized (nothing, as of this audit — the next step requires
an explicit decision from the project owner).

## `customers.email` unique constraint — RESOLVED, not a real defect

**Original note (Phase 4, carried forward through this file and
`PROJECT_HANDOFF_PHASE_4.md` §5 uncorrected until now):** *"`customers.
email` is declared `unique=True, index=True` in the model but the
hand-written `0001_initial_schema.py` migration doesn't include a unique
constraint or index for it."*

**2026-09-07 audit finding: this is false.** Direct inspection of
`0001_initial_schema.py` shows:

```python
op.create_index("ix_customers_email", "customers", ["email"], unique=True)
```

This is a unique index, enforcing the identical database-level
uniqueness guarantee as a table-level `UNIQUE` constraint. No other
migration touches `customers.email`. The constraint the model declares
is already satisfied and has been since migration `0001` was written —
this was never a real defect; it was an uncorrected claim carried across
two phase handoffs and this checklist without anyone re-checking the
actual file. See `docs/PROJECT_ROADMAP.md` §6.3 for the full writeup.
**No code change was made — none was needed.** One minor, genuinely new
caveat: if `alembic revision --autogenerate` is ever run against this
schema, it may propose a spurious migration due to `Index` vs.
`UniqueConstraint` metadata representation, even though runtime behavior
is identical — worth a one-line note for whoever runs autogenerate first,
not worth a migration today.
