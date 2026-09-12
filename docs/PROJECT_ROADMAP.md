# Charter123 — Canonical Project Roadmap

**Status: CANONICAL.** This file is the reconciled baseline produced by a
full forensic audit of the repository against the original Master Build
Prompt (2026-09-07). It supersedes any status claim in `README.md`,
`docs/ARCHITECTURE.md`, `docs/ENVIRONMENT_VARIABLES.md`, or
`docs/PRODUCTION_CHECKLIST.md` wherever those documents disagree with this
one — those files are being corrected alongside this one where the fix is
a documentation-only change, but if a future drift ever puts them back out
of sync, **this file wins.**

Read `docs/SESSION_PROMPT.md` at the start of every new session before
reading anything else, including this file.

---

## 1. Document purpose

Three different things get called "the plan" on this project, and they
are not the same document:

| Concept | What it answers | Where |
|---|---|---|
| **Original Specification** | What was Charter123 supposed to be, in full, on day one? | `MASTER BUILD PROMPT` (the founding document — not stored as a repo file at the time of this audit; treat the copy supplied to this audit session as canonical text and consider committing it to `docs/specification/MASTER_BUILD_PROMPT.md` verbatim so it stops being an external artifact) |
| **Current Implementation** | What does the repository actually contain and do, right now? | `docs/PROJECT_STATE.md`, and ultimately the source code itself |
| **Current Execution Plan** | What should be built next, in what order? | §7 of this file, and `docs/WORK_BREAKDOWN_STRUCTURE.md` |

This file's job is to reconcile the first two and propose the third —
**without silently rewriting history.** Where the original spec and the
repository disagree (either because a deliberate, reasoned decision was
made, or because of drift), both sides of the disagreement are recorded
in §5 and §6, not resolved by quietly picking one.

## 2. Source of truth hierarchy

When any two documents disagree, resolve the disagreement in this order:

1. **The repository itself** (source code, migrations, tests, actually
   running commands) — implementation *fact*.
2. **The Master Build Prompt** — original intended *scope*. It does not
   describe what exists; it describes what was asked for.
3. **This file, `docs/PROJECT_ROADMAP.md`** — the reconciled account of
   how 1 and 2 relate, updated whenever a phase or milestone completes.
4. **`docs/PROJECT_STATE.md`** — a terser, subsystem-by-subsystem
   snapshot of current implementation, meant for fast lookup rather than
   narrative.
5. **`docs/TASK_BOARD.md`** — current authorization. A capability being
   described in this roadmap does **not** mean it is authorized to be
   built right now — check the task board.
6. **`docs/WORK_BREAKDOWN_STRUCTURE.md`** — decomposition of the current
   execution plan into concrete, sequenced tasks.
7. **`docs/MASTER_RULES.md`** — non-negotiable engineering invariants.
   These do not go stale the way status tables do; violating one is a
   defect regardless of what phase is in progress.
8. **`docs/PRODUCTION_CHECKLIST.md`** — line-item Definition-of-Done
   verification status (execution/test evidence), not a roadmap. If it
   ever appears to describe scope or sequencing, that's drift — this file
   and the WBS own sequencing.
9. **Phase and milestone handoffs** (`PROJECT_HANDOFF_PHASE_4.md`,
   `PROJECT_HANDOFF_PHASE_5.md`, `docs/handoffs/*.md`) — frozen historical
   transition records. Excellent evidence for *why* something was built a
   certain way; not to be trusted blindly for *current* status, since the
   repository keeps moving after they're written (this audit itself found
   two cases of exactly that — see §6).

This is the recommended hierarchy from the audit brief, adopted as-is: it
was already sound, and every contradiction found during this audit is
explainable by someone further down this list going stale relative to
someone further up it.

## 3. Original master roadmap (preserved exactly — Master Build Prompt §78)

Phase numbers, names, and scope below are copied from the Master Build
Prompt's own §78 "Implementation order" and cross-referenced against its
§79 "Definition of Done." **Nothing here has been renumbered.** Where the
actual build diverged from this order, that is recorded as a *deviation*
in §6, not by editing the numbers below.

| Phase | Name | Scope (verbatim intent) | Depends on |
|---|---|---|---|
| **1** | Repository & infrastructure | Monorepo scaffold, Docker, PostgreSQL, Redis, FastAPI, Next.js, configuration, logging, health checks | — |
| **2** | Database & mock provider | Database schema, Alembic, airport data, aircraft data, mock flights, `MockAirlineProvider` | 1 |
| **3** | Core booking flows | Flight search, fare quote, booking, booking lookup, booking modification, cancellation, passenger management | 2 |
| **4** | Auth, RBAC & security | Authentication, RBAC, audit logging, rate limiting, security hardening | 3 |
| **5** | Vapi integration | Vapi webhook, Vapi tools, assistant configuration, voice system prompt | 4 |
| **6** | Phone integration | Inbound call, voice booking, voice lookup, voice cancellation, human transfer | 5 |
| **7** | Payments | Stripe, payment webhooks, booking/payment consistency | 4 (auth), 3 (bookings) — not strictly dependent on 5/6 |
| **8** | Notifications | Email, SMS | 3 (bookings exist to notify about) |
| **9** | Admin dashboard | Calls, bookings, customers, analytics UI | 4 (RBAC), 5/6 (call data), 7 (payment data) |
| **10** | Testing & hardening | Security testing, voice testing, E2E, production hardening | all of the above |

Definition of Done for the whole project is the Master Build Prompt's
§79, items 1–34 — reproduced with current status in
`docs/PRODUCTION_CHECKLIST.md`, not duplicated here.

## 4. Actual implementation history (as executed, not as originally ordered)

This is what the repository's own commit-equivalent record (handoffs +
code) shows actually happened, phase-by-phase, in **execution** order:

| Executed as | Corresponds to original phase(s) | What was actually built | Evidence |
|---|---|---|---|
| "Phase 1–3" (one combined session) | 1, 2, 3 | Full monorepo scaffold, FastAPI+SQLAlchemy+Postgres/SQLite-fallback+Redis/in-process-fallback, `AirlineProvider`/`MockAirlineProvider` (deterministic, haversine-based pricing, tiered cancellation fees), flight search/quote/booking/lookup/modify/cancel, passenger management, PNR generation, idempotency (app-level + provider-level), audit logging, passport field encryption, airport/aircraft reference data | `apps/api/app/providers/airline/`, `app/services/{flight,booking,cancellation,passenger}_service.py`, migration `0001`, `tests/test_core_logic.py` (30 tests) |
| "Phase 4" | 4 | `User` model, Argon2id hashing, full session-based auth route set, RBAC (7 roles × 26 permissions — see §6.5), IDOR/ownership fix, booking-verification state machine, Vapi security *architecture* (actor type + authorization matrix, no webhook yet), admin bootstrap, rate limiting + lockout, CSRF, security headers, log redaction, frontend auth pages | migration `0002`, `tests/test_security_core.py` (93 tests), `PROJECT_HANDOFF_PHASE_4.md` |
| "Phase 5.1 → 5.2" | 5, **and most of 6's non-telephony scope** | Vapi webhook route, full tool-call handling, `TOOL_AUTHORIZATION_MATRIX` grown to 23 entries, 21 tool JSON schemas, argument mapping with server-derived idempotency keys, `Call`/`ToolExecution` models, shared verification-token redemption across web+voice, rate limiting wired onto the webhook, `transfer_to_human` corrected to never misleadingly claim a completed transfer | migration `0003`, `tests/test_vapi_core.py` (56 tests), `docs/VAPI.md`, `PROJECT_HANDOFF_PHASE_5.md` |
| "Phase 6, Milestone 1" (repo's own internal label) | **7** (Payments) — see §6.1, this is a numbering deviation, not phase 6 | `Payment` model + state machine, `PaymentProvider`/`MockPaymentProvider`/`StripePaymentProvider`, `PaymentService`, two web routes + Stripe webhook receiver, two new Vapi tools (`create_payment_session`, `get_payment_status`) wired through the same `REQUIRES_VERIFIED_BOOKING` gate as cancel/modify | migration `0004`, `tests/test_payments_core.py` (33 tests) + 11 more in `test_vapi_core.py`/`test_security_core.py`, `docs/PAYMENTS.md`, `docs/handoffs/2026-09-06-phase6-milestone1-payments.md` |
| **This audit** | — (cross-cutting) | Forensic comparison of the above against the Master Build Prompt; no implementation change | This document and its siblings |

Distinguishing originally-planned vs. actual:

- **Implemented early / out of original order:** none in the strict
  sense — Phases 1–5 were executed in their original order. What *did*
  happen is that Phase 5's implementation session absorbed most of
  original Phase 6's *logical* content (voice booking/lookup/cancellation
  — see §6.1) while building what the spec calls Phase 5, and then the
  next session built original Phase 7's content (Payments) under the
  label "Phase 6." Net effect: Payments (spec Phase 7) was pulled forward
  ahead of the literal telephony/live-call piece of spec Phase 6.
- **Deferred, not forgotten:** `refund_payment`, notification delivery,
  admin dashboard, i18n, GDPR export/deletion, call recording/
  transcription, Playwright/E2E and voice test suites, `scripts/
  setup_vapi.py` — see §9 for the full list with reasoning per item.
- **Reworked:** none — no phase's output was rebuilt from scratch after
  being marked done. Bugs were fixed in place (see §12 of each phase
  handoff); no wholesale rework occurred.

## 5. Reconciled current status

| Original Phase | Name | Status | Evidence | Remaining |
|---|---|---|---|---|
| 1 | Repo/infra/Docker/DB/Redis/FastAPI/Next.js/config/logging/health | 🟡 **Written & internally consistent; never executed end-to-end** | `docker-compose.yml`, full `apps/api`/`apps/web` scaffold, `config.py`, `logging.py`, `health.py` all present and `py_compile`-clean (re-verified this audit); `docker compose up` has never been run in any build session to date (no Docker/network access in any sandbox used so far, this audit's included) | Run it, for the first time, in a networked environment with Docker |
| 2 | DB schema/Alembic/airport & aircraft data/mock flights/`MockAirlineProvider` | 🟢 **Complete, logic-verified** | Migrations `0001`–`0004` present and column-checked against models (re-verified this audit, see §6.3 for one correction); 18 airports seeded (all of the spec's §8 minimum list plus 3 more) with the "any London airport" disambiguation group from §6; `MockAirlineProvider` fully covered by `tests/test_core_logic.py` | Run `alembic upgrade head` + `python -m app.db.seed` against a real Postgres |
| 3 | Flight search/quote/booking/lookup/modification/cancellation/passenger mgmt | 🟢 **Complete, logic-verified** | `app/services/{flight,booking,cancellation,passenger}_service.py`, routes wired in `main.py`, `tests/test_core_logic.py` passing | HTTP-level execution against a real running FastAPI instance |
| 4 | Authentication, RBAC, audit logging, rate limiting, security | 🟢 **Complete, core logic executed; HTTP layer written, unexecuted** | 104 dependency-free tests (`test_security_core.py`) actually pass (95 pre-T-6 + 9 new this session, T-6: `StaffAccessTests` for the new `authorize_staff_access()` primitive + one `RbacTests` addition pinning that `CUSTOMER` never holds `admin.*`/`calls.*` permissions); `tests/test_api_security.py` (6 classes, 18 methods) written against real FastAPI `TestClient`, skips cleanly here | Install FastAPI/SQLAlchemy/pytest in a networked environment and run `test_api_security.py` for real — the single highest-leverage unblocked action for the whole project (blocks verifying Phases 4 through 9's HTTP layers all at once) |
| 5 | Vapi integration: webhook, tools, assistant config, voice system prompt | 🟢 **Complete as code; live-call behavior unverified** | `app/api/routes/vapi.py`, `app/core/vapi/*`, `app/core/security/vapi_{authorization,webhook_auth}.py`; 65 dependency-free tests pass (corrected this session from a stale "56", same reason as row 4 above); tool-schema ⇄ authorization-matrix ⇄ dispatch-table consistency independently re-verified this audit (21 schemas, 23 matrix entries, 16 wired dispatch functions — see §6.4 for tools present in spec §19 but absent here) | Live Vapi account + real phone call; `transfer_to_human`'s native `transferCall` companion tool has never been configured. **Updated 2026-09-09 (T-4):** `scripts/setup_vapi.py` (spec §51) is now written (24 dependency-free tests, `OK`) and would automate the `transferCall` configuration too — but has never been run against a real account, so this row's "live-call behavior unverified" still stands unchanged. |
| 6 | Phone integration: inbound call, voice booking/lookup/cancellation, human transfer | 🟡 **PARTIAL — and the repo's own phase labels do not match this row; read §6.1 before trusting any doc that says "Phase 6" without qualification** | The *logic* for voice booking/lookup/cancellation/human-transfer-logging is the same code delivered under "Phase 5" above (`create_booking`/`get_booking`/`cancel_booking`/`modify_booking`/`transfer_to_human` Vapi tools). What has **not** happened: a real phone number connected to a real Vapi assistant, or a real inbound call ever reaching it. **Updated 2026-09-09 (T-4, authorized this session):** `scripts/setup_vapi.py` now exists — written, 24 dependency-free tests passing, never run against a real account | Live phone number + inbound call test (Master Build Prompt §79 items 19–25); running `scripts/setup_vapi.py --apply` against a real Vapi account for the first time; native `transferCall` tool configuration (the script automates creating it, but the transfer itself needs a real call to confirm) |
| 7 | Payments: Stripe, webhooks, booking/payment consistency | 🟡 **PARTIAL — delivered under the repo's own "Phase 6 Milestone 1" label; see §6.1. `refund_payment` (T-3) and payment-link delivery (T-5) closed the two gaps this row used to list** | `create_payment_session`/`get_payment_status`/`refund_payment` implemented, code-reviewed, and (for the dependency-free portions) executed — 46 tests in `test_payments_core.py`; `CancellationService.cancel()` now calls the real provider for a paid cancellation (`docs/PAYMENTS.md` §9); payment-link email/SMS delivery now wired (`docs/PAYMENTS.md` §8, T-5) — content-builder logic executed (31 tests, `test_notifications_core.py`), provider HTTP calls never executed; `StripePaymentProvider` (incl. `refund_payment`) written and cross-checked against live Stripe docs but never executed (no network in any sandbox to date) | A real Stripe test-mode Checkout Session AND a real test-mode refund completing end-to-end; a `refund.updated`/`charge.refunded` webhook subscription (a non-instant refund's `pending`/`requires_action` status never auto-resolves — scoped out of T-3 on purpose); a real email/SMS actually arriving via Resend/Twilio (T-5, blocked on network egress + credentials) |
| 8 | Notifications: email, SMS | 🟡 **PARTIAL — implemented this session (T-5); real-provider execution unverified, same class of gap as Phase 7's Stripe row** | `app/services/email_provider.py` now has `ResendEmailProvider` alongside `MockEmailProvider`; `app/services/sms_provider.py` (new) has `TwilioSmsProvider`/`MockSmsProvider`; both wired to booking-confirmation (email only) and payment-link (email always, SMS for a live voice call) delivery via the new `NotificationService`; 31 dependency-free tests for the content-builder logic (`tests/test_notifications_core.py`) actually pass | Real `RESEND_API_KEY`/`TWILIO_*` credentials + network egress (neither exists in any sandbox this project has used) to confirm an actual email/SMS arrives; see `docs/TASK_BOARD.md`'s T-5 entry |
| 9 | Admin dashboard | 🟡 **PARTIAL — implemented this session (T-6); FastAPI/SQLAlchemy execution unverified (same class of gap as Phase 8's row), Next.js pages syntax-checked only, not type-checked against a real toolchain** | `/api/v1/customers` (list/get/patch), `/api/v1/calls` (list/get), `/api/v1/admin/{bookings,bookings/{id},analytics}` implemented, code-reviewed; new `authorize_staff_access()` authorization primitive executed and tested (8 tests, `StaffAccessTests`); `app/core/admin/analytics.py`'s rate/revenue arithmetic executed and tested (13 tests, `tests/test_admin_core.py` — deliberately has no "quote conversion rate" metric, not computable from what's persisted today, see that module's docstring); 7 Next.js admin pages + layout gate written, zero `TS1xxx` syntax errors under a standalone `tsc --noResolve` pass, never run against a real `node_modules`/`next build` | A real Postgres + full dependency stack (same as every other phase's remaining item) to execute the FastAPI layer for real; `npm install` in a networked environment to run a real `tsc --project`/`next build`/browser click-through; see `docs/TASK_BOARD.md`'s T-6 entry for the full "Testing status" breakdown, including which pre-existing diagnostics were cross-checked as harness artifacts rather than assumed harmless |
| 10 | Testing & production hardening | 🟡 **PARTIAL** | **289/289 dependency-free tests pass — re-executed and confirmed this session (2026-09-11, T-6: +22 over the prior 267 — 9 in `test_security_core.py`, 13 new in `test_admin_core.py`).** `tests/test_api_security.py` and `tests/test_vapi_api.py` are written (8 skips, confirmed, unchanged by T-6) but have never run against real FastAPI. `tests/{e2e,integration,voice}/` contain only `README.md` placeholders — no Playwright, no real-DB integration tests, no voice conversation test suite (spec §56) exist yet | Install the full stack and run the FastAPI-level suites for real; write the Playwright E2E suite (Phase 9's admin pages now exist as a candidate surface for this, alongside a customer-facing booking UI which still doesn't); write the voice conversation test suite from spec §56 |

Legend matches the audit brief: 🟢 COMPLETE · 🟡 PARTIAL · 🔴 NOT
IMPLEMENTED · ⚠️ DEFECTIVE · 🔵 DEFERRED BY DECISION · ⚪ NOT VERIFIABLE.
No row above uses 🟢 merely because a file exists — each 🟢 has an
attached, dependency-free, actually-executed test count.

## 6. Contradictions found (recorded, not silently resolved)

### 6.1 Phase numbering: Payments was built as "Phase 6," but the spec's Phase 6 is telephony

**A. Master Build Prompt vs. repository's own internal labels.** The
original spec's Phase 6 is "Phone integration" (inbound call, voice
booking/lookup/cancellation, human transfer); Phase 7 is "Payments."
`docs/handoffs/2026-09-06-phase6-milestone1-payments.md` and
`docs/PAYMENTS.md` both label the Stripe payments work "Phase 6
Milestone 1." That work is, by original scope, **Phase 7** content.

**B. This was flagged, not missed, by the session that did it** —
`PROJECT_HANDOFF_PHASE_5.md` §19 explicitly says payments were "already
named as Phase 7 in the original roadmap — worth confirming numbering
hasn't shifted" before the next session went ahead and built it as
"Phase 6" anyway, without a recorded confirmation either way.

**C. Net effect on actual scope, independent of the label:** most of
original Phase 6's *logic* (voice-driven booking/lookup/cancellation,
transfer-to-human) was already delivered as part of what the repo calls
"Phase 5" — Vapi tool dispatch for `create_booking`/`get_booking`/
`cancel_booking`/`modify_booking`/`transfer_to_human` *is* "voice
booking/voice lookup/voice cancellation/human transfer." What remains of
original Phase 6, uniquely, is the literal telephony piece: a connected
phone number and a real inbound call — neither of which exist yet.
**Updated 2026-09-09 (T-4):** `scripts/setup_vapi.py` (spec §51), the
third item this paragraph used to list as not existing, is now written
(see `docs/TASK_BOARD.md` T-4) but has never been run against a real
account, so it closes none of Phase 6's remaining gap by itself yet.
Payments (spec Phase 7) was, in substance,
pulled forward ahead of that remaining telephony sliver.

**Resolution for this roadmap:** §3's phase numbers are preserved
exactly, per the audit's own instruction not to renumber. §5's status
table reflects reality against those preserved numbers — Phase 6 is
correctly shown PARTIAL (telephony not done), Phase 7 is correctly shown
PARTIAL (payments milestone 1 done, `refund_payment` not done),
regardless of what the source documents from that session called
themselves. **Do not create a `PROJECT_HANDOFF_PHASE_6.md`** using the
repo's internal numbering — if/when original Phase 6 (telephony) is
actually completed, that is the point to write it; the payments work has
its own, correctly-scoped milestone handoff already.

### 6.2 Stale documentation asserting features are unbuilt when they exist

Confirmed by direct inspection (not merely by trusting the self-report in
`docs/handoffs/2026-09-06-phase6-milestone1-payments.md` §15, though that
self-report turned out to be accurate):

- `README.md`'s "Current status" line: *"Phases 1–4... The Vapi voice
  layer, payments, notifications, and the admin dashboard are not built
  yet."* — Vapi (Phase 5) and a payments milestone (Phase 7 M1) both
  exist. **Fixed as part of this audit** — see the "Documentation
  changes" list at the end of this file.
- `docs/ARCHITECTURE.md`'s top banner: *"Everything from §5 of the build
  spec ('Vapi' onward)... is not yet built."* — same staleness. **Fixed.**
- `docs/ARCHITECTURE.md`'s "Trust boundary" section warned that
  `x-charter123-call-id` "is not yet verified against anything... there's
  no Vapi integration yet." Partially stale: real Vapi tool calls now go
  through the authenticated `/api/v1/vapi/webhook` path, which derives
  `call_id` from the *webhook body itself* (`message.call.id`), reachable
  only after the shared-secret check passes — not from a client header.
  **However**, the direct REST routes in `app/api/routes/bookings.py`
  still read this same header name unauthenticated, purely to build the
  audit log's human-readable `actor` string (e.g. `vapi_call:<value>`) —
  see §8.5 for why this is a real, if minor, residual finding from this
  audit, not fully resolved by Phase 5. **Docs updated to reflect the
  current, more nuanced picture instead of either extreme.**
- `docs/ENVIRONMENT_VARIABLES.md`'s `VAPI_API_KEY` row: *"unused until
  Phase 5... no live Vapi integration exists in this phase."* **Fixed.**
- `docs/PRODUCTION_CHECKLIST.md` items 16–25 (Vapi webhook/tools/
  Assistant/inbound-call) still read "⬜ Not started — Phase 5," and its
  "Explicitly out of scope" section still lists the Vapi implementation
  as not started. **Fixed as part of this audit** — see §8 below and the
  updated checklist file itself.

None of `docs/SECURITY.md`, `docs/VAPI.md`, or `docs/PAYMENTS.md` were
found to have this problem — all three were already current as of this
audit and needed no correction.

### 6.3 A previously-recorded gap that does not actually exist

`PROJECT_HANDOFF_PHASE_4.md` (§5, "Pre-existing Phase 1-3 issue"),
`docs/PRODUCTION_CHECKLIST.md` (closing section), and this project's own
prior-session memory all assert: *"`customers.email` is `unique=True,
index=True` in the model but the hand-written `0001_initial_schema.py`
migration has neither."*

**This audit inspected `0001_initial_schema.py` directly. It is false.**
The migration contains:

```python
op.create_index("ix_customers_email", "customers", ["email"], unique=True)
```

This is a unique index, which enforces the identical database-level
uniqueness guarantee as a table-level `UNIQUE` constraint (in PostgreSQL,
a `UNIQUE` constraint *is* implemented as a unique index internally) —
`Customer.email`'s `unique=True` in the model is already satisfied.
Grepped every migration file for any other `customers`/`email` reference
to rule out a later migration dropping it: none exists. **This claim has
been carried forward, uncorrected, across at least two phase handoffs
and one production-checklist revision, without anyone re-verifying it
against the actual migration file.** It is exactly the failure mode this
audit was commissioned to catch. Marked ✅ **RESOLVED — verified by
direct inspection** in `docs/PRODUCTION_CHECKLIST.md`; no code change
was needed because there was never a real defect.

One genuine, much smaller caveat: SQLAlchemy represents `Column(unique=
True)` as a `UniqueConstraint` in ORM metadata but this migration created
a plain `Index(..., unique=True)` instead — functionally identical at the
database level, but if `alembic revision --autogenerate` is ever run
against this table, it may propose a spurious no-op migration due to that
representational mismatch. Worth a one-line note for whoever first runs
autogenerate against this schema; not worth a migration today.

### 6.4 Tools in the original spec's §19 list that were never registered at all

`docs/VAPI.md` carefully tracks 5 "INTENTIONALLY UNAVAILABLE" tools
(`add_baggage`, `get_seat_options`, `select_seat`, `create_support_
ticket`, `create_callback_request`) — each still registered in
`tool_schemas.py` with `implemented=False`, so the LLM can be told they
exist and aren't available yet, per that document's own stated policy.

This audit greped `app/core/vapi/tool_schemas.py` and
`app/core/security/vapi_authorization.py` for eight more tools named in
the Master Build Prompt's §19 and found **no trace of them at all** —
not implemented, not registered as unavailable, not mentioned in any
doc's gap list:

`update_passenger`, `get_customer`, `create_customer`, `update_customer`,
`end_call`, `get_airport`, `search_airports`, `get_faq`.

Notes on each, since "missing" means different things here:

- `update_passenger` — passenger data can be added (`add_passenger`) and
  removed (`remove_passenger`) via Vapi, but not corrected in place; the
  REST layer's `passenger_service.py` may or may not support an update
  path independent of Vapi — not checked in this pass, flagged for the
  next session.
- `get_customer`/`create_customer`/`update_customer` — **updated
  2026-09-11 (T-6):** the `/api/v1/customers` route family now exists
  (list/get/patch — `app/api/routes/customers.py`), and `Customer` rows
  are still only ever created implicitly, inside `create_booking`, per
  `docs/SECURITY.md` §3's documented design (T-6 deliberately did not
  add a standalone "create a customer with no booking" admin action —
  see `docs/TASK_BOARD.md`'s T-6 entry, "Decisions/deviations" #1). A
  `get_customer`/`update_customer` Vapi tool now DOES have a backing
  service to call (`CustomerService`); `create_customer` as a Vapi tool
  still wouldn't, by design — this is T-8's scope, now unblocked.
- `end_call` — Vapi's own platform may make a dedicated tool
  unnecessary (a native end-call capability may exist the way
  `transferCall` does for transfers — not independently confirmed in
  this audit; needs an external-Vapi-docs check before deciding whether
  this is a real gap or a non-issue).
- `get_airport`/`search_airports` — `Airport` reference data exists and
  is seeded (18 rows, `app/models/airport.py`), and disambiguation
  groups exist in `reference_data.py`, but nothing exposes this to a
  caller as a queryable REST or Vapi tool.
- `get_faq` — no FAQ/knowledge-base model exists anywhere (Phase-8/
  Phase-10-adjacent territory per the original spec's §46); this is a
  genuine, not-yet-scoped domain gap, not a wiring gap.

This is a new finding from this audit, not previously tracked in any
document. Added to `docs/WORK_BREAKDOWN_STRUCTURE.md` and
`docs/PRODUCTION_CHECKLIST.md`'s gap list.

### 6.5 Permission count: docs say 25, the code has 26

`docs/SECURITY.md` §4 and this project's prior-session summary both say
"7 roles × 25 permissions." Counting `Permission` enum members in
`app/core/security/rbac.py` directly gives **26** (the extra one appears
to be `PAYMENTS_CREATE`, needed once payments existed, alongside the
pre-existing `PAYMENTS_READ`/`PAYMENTS_REFUND`). Not a defect — RBAC
correctly grew when the payment surface needed a `payments.create`
permission distinct from `payments.read` — just a stale number in prose.
Corrected here; `docs/SECURITY.md` left as-is since it's a cosmetic
one-digit slip, not worth a diff on its own (fold into the next real edit
of that file).

### 6.6 A minor, previously undocumented residual finding: audit-log actor spoofing on the direct REST routes

`app/api/routes/bookings.py`'s direct REST endpoints (`POST /api/v1/
bookings`, `/lookup`, `/cancel`, `/modify`) read `x-charter123-call-id`
straight off the request header, with **no authentication on that header
at all**, and use it only to build the audit log's `actor` string (e.g.
`vapi_call:{call_id}`) — never for an authorization decision. This is
**not** a privilege-escalation bug: nothing is unlocked based on this
header's value, and these routes' actual authorization runs through the
same `authorize_*` functions everything else does, which never read it.

It **is** an audit-trail integrity gap, and it is exactly the pattern the
Master Build Prompt's §20 warns about generally ("Never trust
`x-user-id`, `customerId`, `bookingId`, **or similar client-supplied
identifiers**"): any caller hitting these REST routes directly (not
through the authenticated Vapi webhook) can put an arbitrary string in
this header and have it appear in the audit log as if it came from that
Vapi call — including a real call's actual ID, if guessed or observed.
The real Vapi webhook path (`app/api/routes/vapi.py`) does **not** have
this problem: it derives `call_id` from `message.call.id` inside the
webhook body itself, reachable only after the shared-secret check
already passed.

Recommended fix (not made in this audit — out of scope, see §11): stop
reading this header on the public REST routes entirely (the anonymous
booking flow doesn't need it for anything but a debug label), or bind it
to something authenticated. Recorded in
`docs/PRODUCTION_CHECKLIST.md`'s known-issues list and
`docs/WORK_BREAKDOWN_STRUCTURE.md`.

## 7. Current execution plan (proposed — not authorization; see `docs/TASK_BOARD.md`)

This does **not** overwrite §3's original roadmap. It is this audit's
recommendation for what to do next, informed by both.

```
STEP 0 (already done by this audit) — Reconcile documentation
   v
STEP 1 — Get the FastAPI/SQLAlchemy stack actually installed and running
         somewhere with network access. Run tests/test_api_security.py
         and tests/test_vapi_api.py for real. This has been the single
         largest, cheapest, most repeatedly-deferred unblock since Phase 4.
   v
STEP 2 — Decide, explicitly, how to treat the Phase 6/7 numbering question
         (§6.1): continue payments as its own track under whatever label,
         and treat "Phase 6 — telephony" as still open? Or renumber
         going forward with an explicit decision recorded here?
   v
STEP 3a (Phase 7 remainder) — refund_payment (staff/admin-only tool),
         a real Stripe test-mode Checkout Session end-to-end (needs a
         live account), payment-link delivery (blocked on Phase 8)
   v
STEP 3b (Phase 6 remainder, telephony) — scripts/setup_vapi.py (now
         written, T-4, 2026-09-09 — see §8), connect a
         real phone number, one real inbound call, transferCall config
   v
STEP 4 (Phase 8) — Real email provider (Resend/SMTP) + real SMS provider
         (Twilio), wire booking confirmation + payment-link delivery
   v
STEP 5 (Phase 9) — Admin API routes (calls, bookings, customers,
         payments, analytics) + Next.js admin UI. **Done, T-6,
         2026-09-11 — see §8.**
   v
STEP 6 (Phase 10) — Playwright E2E (needs Phase 9's/customer-facing web
         pages), the voice conversation test suite (spec §56), full
         security-testing pass, production hardening
   v
Ongoing — close the §6.4/§6.6 gaps found in this audit whenever the
          relevant subsystem (customers, telephony) is next touched
```

3a and 3b can proceed in parallel — they don't block each other. Exit
criteria, dependencies, and test requirements for each step are detailed
in `docs/WORK_BREAKDOWN_STRUCTURE.md`.

## 8. Current position

**Read this section first if you are a new session picking this up.**

- **Last completed (closed) work:** T-3 (Phase 7 remainder —
  `refund_payment`, 2026-09-08): `PaymentProvider.refund_payment()`
  implemented in both `MockPaymentProvider` and `StripePaymentProvider`;
  `CancellationService.cancel()` now actually calls it for a paid
  cancellation instead of only flipping `payment_status` locally (see
  risk (2) below — **closed**, moved out of this list); a new staff-only
  `POST /api/v1/payments/refunds` route for a manual/goodwill refund
  independent of cancellation. See
  `docs/handoffs/2026-09-08-t3-refund-payment.md` and
  `docs/PAYMENTS.md` §9 for the full design. 236/236 dependency-free
  tests pass (13 new, all in `test_payments_core.py` — re-executed and
  confirmed this session).
- **Before that:** Phase 7 Milestone 1 (Payments — Stripe Checkout
  Sessions: `create_payment_session`, `get_payment_status`), labeled
  "Phase 6 Milestone 1" in its own handoff — see §6.1 for why that label
  doesn't match the original spec's numbering.
- **Earlier the same day (2026-09-09):** T-4 (Phase 6 remainder —
  telephony) moved from Proposed to **AUTHORIZED** on the project
  owner's explicit instruction, and `scripts/setup_vapi.py` (spec §51,
  WBS-2.1) was written — idempotent create-or-update for the 21
  registered Vapi tools, the native `transferCall` tool, the Assistant,
  and phone-number attachment, cross-checked against Vapi's current API
  docs (fetched that session; includes one genuinely new finding —
  Vapi's move to a dashboard-managed Custom Credentials webhook-auth
  system, which does not contradict what
  `vapi_webhook_auth.py` already had on record). 24 new dependency-free
  tests (`scripts/test_setup_vapi.py`), executed: `OK`. **T-4 is NOT
  closed** — see its `docs/TASK_BOARD.md` entry: WBS-2.2 through 2.5 (a
  real phone number, a real inbound call, live `transferCall`
  verification) remain BLOCKED on the same external dependency (a live
  Vapi account) the task always named, compounded by this sandbox's
  network restriction.
- **This session's work (2026-09-09):** T-5 (Phase 8 — notifications)
  moved from Proposed to **AUTHORIZED** on the project owner's explicit
  instruction ("Execute and authorize T-5"), same mechanism T-4 used.
  `app/core/notifications/content.py` (new, dependency-free content
  builders), `app/services/email_provider.py` (extended: 2 new methods
  + `ResendEmailProvider`), `app/services/sms_provider.py` (new:
  `SmsProvider` interface + `MockSmsProvider` + `TwilioSmsProvider`),
  and `app/services/notification_service.py` (new orchestration layer,
  wired into `BookingService.create_booking`/`PaymentService.
  create_payment_session` as an optional, best-effort, non-blocking
  system side effect — never a Vapi tool, MASTER_RULES §6). Closes the
  gap `docs/PAYMENTS.md` §8 documented for payment-link delivery, and
  spec §44's booking-confirmation requirement, both for the first time.
  31 new dependency-free tests (`tests/test_notifications_core.py`),
  executed: `OK`. Resend's and Twilio's request/response/error shapes
  were fetched from each provider's own current API reference this
  session, not assumed from training data — same discipline T-3/T-4
  applied to Stripe/Vapi. **T-5 is NOT closed** — see its
  `docs/TASK_BOARD.md` entry: real Resend/Twilio execution against live
  accounts remains BLOCKED on the same external dependency (network
  egress + real credentials) every other real-provider integration in
  this project has hit. Two pre-existing gaps were found (not
  introduced) and left honestly unfixed as out of scope: `Booking.
  cancellation_deadline` is never populated anywhere in this codebase,
  and `Booking` does not persist which cabin class was booked — see
  `docs/TASK_BOARD.md`'s T-5 entry, "Known gap this task did not fix."
- **This session's work (2026-09-11):** T-6 (Phase 9 — admin dashboard)
  moved from Proposed to **AUTHORIZED** on the project owner's explicit
  instruction ("Execute and authorize T-6"), same mechanism T-4/T-5
  used. New authorization primitive `authorize_staff_access()`/
  `require_staff_permission()` (closes a real gap: the bare `CUSTOMER`
  role holds `customers.read` too, for its own profile — a naive
  list-all-customers check would let a customer enumerate every OTHER
  customer); new dependency-free `app/core/admin/analytics.py` (rate/
  revenue math, no "quote conversion rate" — not computable from what's
  persisted today, see that module's docstring); `CustomerService`/
  `CallService`/`AdminService` (new); `/api/v1/customers`,
  `/api/v1/calls`, `/api/v1/admin/{bookings,analytics}` routes (new);
  7 Next.js admin pages + a staff-only layout gate (new — this app's
  first `components/` directory). 22 new dependency-free tests (9 in
  `test_security_core.py`, 13 new in `tests/test_admin_core.py`),
  executed: `OK`, 289/289 total. A pre-existing inconsistency was found
  (not introduced) and worked around, not silently fixed: every current
  `record_audit_event()` call for `resource="booking"` uses
  `resource_id=pnr`, never `str(booking.id)` — confirmed by grep; see
  `docs/TASK_BOARD.md`'s T-6 entry, "Decisions/deviations" #3. **T-6 is
  NOT closed** — same class of gap as T-4/T-5: `npm install`/
  `pip install` + real network egress are needed to run the FastAPI
  layer and get a real `tsc --project`/`next build` against the new
  frontend, neither of which this sandbox can do.
- **This session's work (2026-09-12):** T-7 (Phase 10 — testing &
  hardening) moved from Proposed to **AUTHORIZED** on the project
  owner's explicit instruction ("Execute and authorize T-7"), same
  mechanism T-4/T-5/T-6 used. Three scope items: (1) `tests/e2e/admin/`
  (new) — a real Playwright suite against the actual admin dashboard
  component source (T-6); (2) `apps/api/tests/test_voice_
  conversation_core.py` (new, 29 tests, dependency-free, **executed**:
  `OK`) — one class per spec-§56 scenario WBS-6.2 names (six, not the
  seven claimed — the original spec text isn't committed in this repo to
  check the mismatch against, reproduced honestly rather than resolved
  by invention); (3) a security-testing pass repeating
  `PROJECT_HANDOFF_PHASE_5.md` §11's checklist against T-3/T-4/T-5/T-6.
  Two real bugs found and fixed: `apps/web/app/login/page.tsx` silently
  ignored the `next=` redirect param `admin/layout.tsx` depends on
  (found while writing the Playwright suite); `app/core/encryption.py`
  imported `app.core.config`/`app.core.logging` at module level even
  though `mask_for_speech()` needs neither, which meant the "never
  reveal a passport number" function had never been importable by this
  project's own dependency-free test tier before today (found while
  writing the voice suite, now lazy-imported, unblocked). One more real
  finding from the security pass, also fixed:
  `notification_service.py`'s failure-audit metadata stored the raw
  Twilio/Resend error message verbatim, which for several of those
  providers' own documented error codes echoes the customer's phone/
  email back — and T-6's new admin audit endpoint renders that field
  unredacted. 318/318 dependency-free tests pass (29 new, all in the new
  suite — re-executed and confirmed this session). **T-7 is NOT fully
  closed:** the customer-facing half of the Playwright suite (search →
  book → lookup → cancel → modify → human transfer) was not built — no
  such pages exist in `apps/web/app/` yet, and building them would be
  new production frontend surface undertaken unilaterally under a
  "testing & hardening" task, not something this session's scope covers;
  see `docs/TASK_BOARD.md`'s T-7 entry and §6.1-style open-question
  framing just below. The admin Playwright suite and the notification
  fix are otherwise the same "written, reviewed, NOT executed" class as
  T-4/T-5/T-6 (no Node network access to `npm install`; no SQLAlchemy to
  import `notification_service.py`).
- **Current authorized work:** T-1 (install & execute the FastAPI/
  SQLAlchemy test layer for real) remains authorized and still
  **BLOCKED** — re-confirmed again this session (`python3 -c "import
  fastapi"` / `sqlalchemy` / `stripe` / `httpx` / `pydantic` all raise
  `ModuleNotFoundError`; network still disabled in this sandbox).
  Identical to every prior sandbox since Phase 4; not a new finding. T-4,
  T-5, T-6, and now T-7 (its Playwright/notification-fix halves — the
  voice-conversation suite is NOT blocked, it already ran) are also
  authorized and also **BLOCKED**, for the same underlying reason plus
  their own further dependencies (a live Vapi account for T-4; real
  Resend/Twilio credentials for T-5; `npm install` + a real Postgres for
  T-6; `npm install` + a live web+api+db stack + a bootstrapped staff
  account for T-7's Playwright half) — see `docs/TASK_BOARD.md`'s T-1,
  T-4, T-5, T-6, and T-7 entries for the full attempt logs.
- **Next work (candidates, not yet chosen):** Step 1 (get the full stack
  installed and run the HTTP-level test suites for real) is the
  recommended first move regardless of which feature comes next, because
  every remaining phase's HTTP layer is equally unverified and this is
  the cheapest way to convert "written, reviewed" into "known to work" or
  "found a real bug" across all of them at once — this now includes
  T-3's `refund_payment`, T-5's notification-service changes, T-6's
  admin routes, and T-7's `notification_service.py` fix too. Running
  `scripts/setup_vapi.py --apply` for the first time, against a real
  Vapi account, is the equivalent next move for T-4; setting real
  `RESEND_API_KEY`/`TWILIO_*` values and confirming an actual email/SMS
  arrives is the equivalent next move for T-5; running `npm install` and
  a real `next build`/browser click-through is the equivalent next move
  for T-6; `npm install` in `tests/e2e/admin/` plus `npx playwright
  test` against that same running stack is the equivalent next move for
  T-7's admin suite. T-8 (the Vapi tools this audit found missing in
  §6.4) is now unblocked — both of its candidate dependencies (T-4's
  calls, T-6's customers) are done. A product/planning decision on the
  customer-facing booking UI's sequencing (see T-7's entry) would unblock
  the other half of T-7's Playwright scope, the same way §6.1's
  numbering decision remains an open planning call rather than a
  technical blocker.
- **Blocked work:** anything requiring network access this build
  environment doesn't have (installing FastAPI/SQLAlchemy/`stripe`/
  `httpx`, `npm install`, `docker compose up`, a live Vapi account, a
  live Stripe test-mode account, a live Resend/Twilio account) —
  confirmed still blocked this session too (`pip install fastapi` fails
  here exactly as it has since Phase 4; `npm install` has never been
  attempted successfully in any sandbox this project has used either).
- **Important known risks:** (1) the Phase 6/7 numbering question in
  §6.1 is unresolved and should be decided explicitly rather than left
  ambiguous going forward; (2) ~~`CancellationService.cancel()` flips
  `payment_status` to `REFUNDED` without ever calling `PaymentProvider`~~
  — **fixed in T-3** (docs/PAYMENTS.md §9); a related, narrower gap
  remains in its place: no webhook subscription for Stripe's
  `refund.updated`/`charge.refunded` events, so a non-instant
  (`pending`/`requires_action`) refund never auto-resolves on its own —
  deliberately out of T-3's scope, see `docs/PAYMENTS.md` §9's last
  bullet; (3) the audit-log actor-spoofing gap in §6.6; (4) `Booking.
  cancellation_deadline` is never populated anywhere in this codebase —
  found by T-5 while building the booking-confirmation email, not
  fixed (out of T-5's scope; see §9 below); (5) the customer-facing
  booking UI's sequencing is unresolved (T-7, 2026-09-12) — no
  search/book/lookup/cancel/modify pages exist in `apps/web/app/` yet,
  which blocks the customer-facing half of the Phase 10 E2E suite and
  was already flagged as an open question in WBS-6.1's own wording
  before T-7 started; (6) `cancellation_service.py`'s Stripe-refund-
  failure audit metadata may carry the same raw-provider-error-message
  PII exposure T-7 fixed for `notification_service.py`'s Twilio/Resend
  case, unconfirmed against live Stripe error text — see
  `docs/PROJECT_STATE.md`'s "Known residual security/integrity
  findings."

## 9. Known gaps and risks

**Missing features (by original phase):**
- Phase 6: live telephony connection (a real number, a real inbound
  call), native `transferCall` verification against a real call.
  **Updated 2026-09-09 (T-4):** `scripts/setup_vapi.py` itself is now
  written — see below, no longer listed as missing, only as unexecuted.
- Phase 7: ~~payment-link delivery~~ closed by T-5, 2026-09-09 — real
  provider execution still unverified (`refund_payment` closed by T-3,
  2026-09-08.)
- Phase 8: real email provider, real SMS provider. **Updated
  2026-09-09 (T-5):** both now implemented (`ResendEmailProvider`/
  `TwilioSmsProvider`) — see §5's Phase 8 row; no longer listed as
  missing, only as unexecuted against a live account.
- Phase 9: admin dashboard — **updated 2026-09-11 (T-6):** implemented
  this session (`/api/v1/customers`, `/api/v1/calls`,
  `/api/v1/admin/{bookings,analytics}` + 7 Next.js pages) — no longer
  listed as missing, only as unexecuted against a real FastAPI/
  SQLAlchemy/Next.js toolchain; see §5's Phase 9 row and
  `docs/TASK_BOARD.md`'s T-6 entry for the full account.
- Phase 10: Playwright E2E, voice conversation test suite — entirely
  absent (placeholders only).
- **Newly identified this session (T-5, 2026-09-09):** `Booking.
  cancellation_deadline` is a nullable column declared in the model,
  migration, and `BookingOut` schema, but nothing in `create_booking`/
  `modify_booking` (or anywhere else) ever sets it — confirmed by grep
  before writing the booking-confirmation notification's content logic,
  not assumed. `Booking` also does not persist which `CabinClass` was
  actually booked, so T-5's baggage-allowance lookup for that same email
  defaults to `CabinClass.ECONOMY` rather than the fare purchased. Both
  are pre-existing gaps in the booking data model, not caused by any
  notification code — flagged here rather than silently worked around;
  see `app/core/notifications/content.py`'s docstring for how the
  notification content honestly handles both (a generic sentence, never
  a guessed number/date) and `docs/TASK_BOARD.md`'s T-5 entry for the
  full account.
- Cross-cutting domain gaps: seat selection/seat map, baggage mutation,
  support tickets, callback requests, FAQ/knowledge base, i18n (German/
  Persian per spec §41), GDPR export/deletion endpoints, call recording/
  transcription, retention-policy enforcement jobs (variables exist,
  nothing reads them).
- Newly identified this audit (§6.4): `update_passenger`, `get_customer`/
  `create_customer`/`update_customer`, `end_call`, `get_airport`/
  `search_airports`, `get_faq` — no Vapi tool registered at all, not even
  as a placeholder. **Updated 2026-09-11 (T-6):** `get_customer`/
  `update_customer` now have a backing service to call
  (`CustomerService`, via T-6) — the remaining gap for those two is
  purely "no Vapi tool schema/dispatch function wired to it yet," not
  "nothing to wire to," which is T-8's scope now.
- **Newly identified this session (T-6, 2026-09-11):** every current
  `record_audit_event()` call site for `resource="booking"`
  (`booking_service.py`/`cancellation_service.py`/`passenger_service.py`
  — confirmed by grep, all of them) writes `resource_id=pnr`, never
  `resource_id=str(booking.id)`. `AuditLog.resource_id` is an
  unconstrained `String` column with nothing enforcing which shape a
  future call site uses — T-6's admin booking-detail route works around
  this defensively (queries both, merges), but the underlying
  inconsistency-risk is not structurally fixed. See
  `docs/TASK_BOARD.md`'s T-6 entry, "Decisions/deviations" #3, and
  `app/services/admin_service.py::AdminService.get_booking_detail`'s
  docstring.

**Security/architecture gaps:**
- Audit-log actor spoofing on direct REST routes via `x-charter123-call-
  id` (§6.6) — minor, no privilege escalation, real integrity issue.
- `RATE_LIMIT_PROFILES["vapi_webhook"]`/`["vapi_tool"]` are unvalidated
  placeholder numbers, not tuned against real traffic.
- A genuinely *concurrent* (not sequential) double-delivery of the same
  `vapi_tool_call_id` could still race past the `ToolExecution` unique
  constraint (mitigated by independent idempotency at the booking-mutation
  layer, not eliminated at this layer).
- No `X-Forwarded-For` handling for the Vapi webhook's source-IP rate
  limit key — meaningless behind a reverse proxy until added.
- `InMemoryIdempotencyStore` and the in-process Redis/rate-limit
  fallbacks are single-process only — fine for dev, unsafe for a
  multi-instance production deployment.

**Testing gaps:** see Phase 10 row in §5 — this is the single largest
category of "written but not known to work" in the whole project.

**Documentation gaps:** closed by this audit for `README.md`,
`docs/ARCHITECTURE.md`, `docs/ENVIRONMENT_VARIABLES.md`,
`docs/PRODUCTION_CHECKLIST.md`. The Master Build Prompt itself is not
currently committed to the repository as a file — recommend adding it
verbatim at `docs/specification/MASTER_BUILD_PROMPT.md` so future
sessions don't depend on it being pasted into a chat.

**Production blockers:** no networked build/test environment has ever
been available (Phase 4 through this audit, inclusive) — nothing in the
FastAPI/SQLAlchemy/Stripe/Docker layer has ever actually executed.
This is the single largest gap between "should work" and "known to
work" across the entire project, repeated in every phase's own
documentation, and confirmed unchanged by this audit.

**External dependency blockers:** a live Vapi account + phone number; a
live Stripe test-mode account; eventually a real email/SMS provider
account.

## 10. Explicit non-goals / deferred items

These are **deliberate, reasoned deferrals**, not forgotten work — do not
"discover" them as new gaps in a future session without first reading why
they were deferred:

- **`flights`/`flight_segments`/`fares` are not persisted tables**, despite
  being listed in the Master Build Prompt's §28. `docs/ARCHITECTURE.md`
  documents the reasoning in full: an airline's live schedule/availability
  is provider-owned data, caching it risks staleness, and a real GDS
  integration would discourage it. `Booking` stores an itinerary
  *snapshot* instead. If this is ever revisited, add a `flights` table as
  a cache in front of the provider, not as its replacement.
- **`refund_payment` is reserved but unbuilt on purpose** — already present
  in `TOOL_AUTHORIZATION_MATRIX` as `STAFF_OR_ADMIN_ONLY` since before any
  payment backend existed, specifically so the authorization boundary
  would already be correct the day it's implemented.
- **Payment-link delivery (email/SMS) was explicitly scoped out of Phase
  7 Milestone 1** — `docs/PAYMENTS.md` §8 says outright: "do not silently
  add Resend/Twilio/any delivery provider to close this gap — it needs
  its own milestone with its own review."
- **Multilingual voice (German/Persian, spec §41) was never started** —
  `docs/VAPI.md` says so explicitly and warns not to configure a
  production multilingual Assistant based on anything in that document.
- **Amadeus/Sabre adapters are placeholders that raise `NotImplementedError`
  on purpose** — spec §5/§40 explicitly forbid fabricating undocumented
  third-party APIs; this is compliance with that instruction, not a gap.

## 11. Required reading for future sessions

A new coding session must read, in this order, before writing any code:

1. `docs/SESSION_PROMPT.md` (paste-at-start-of-session bootstrap)
2. `docs/PROJECT_ROADMAP.md` (this file)
3. `docs/PROJECT_STATE.md`
4. `docs/TASK_BOARD.md`
5. `docs/MASTER_RULES.md`
6. The relevant section(s) of `docs/WORK_BREAKDOWN_STRUCTURE.md`
7. The latest applicable handoff in `docs/handoffs/` (or the root-level
   `PROJECT_HANDOFF_PHASE_*.md` files for phase-level context)

Then inspect the actual relevant source code before implementing
anything. **Do not rely on previous chat history** — a different chat, a
different model, or a compacted context window may be missing exactly
the information that made a prior decision correct. Trust the repository
over any document, and trust dated documents over undated memory.

---

## Documentation changes made by this audit

- **Created:** `docs/PROJECT_ROADMAP.md` (this file), `docs/PROJECT_STATE.md`,
  `docs/TASK_BOARD.md`, `docs/MASTER_RULES.md`,
  `docs/WORK_BREAKDOWN_STRUCTURE.md`, `docs/SESSION_PROMPT.md`.
- **Corrected (drift fixed):** `README.md` ("Current status" line, "What's
  next" section), `docs/ARCHITECTURE.md` (top banner, trust-boundary
  section), `docs/ENVIRONMENT_VARIABLES.md` (`VAPI_API_KEY` row),
  `docs/PRODUCTION_CHECKLIST.md` (items 16–25, "explicitly out of scope"
  section, the `customers.email` closing note, new rows for Phase 6/7).
- **Left untouched, as historical records, per audit policy:**
  `PROJECT_HANDOFF_PHASE_4.md`, `PROJECT_HANDOFF_PHASE_5.md`,
  `docs/handoffs/2026-09-06-phase6-milestone1-payments.md`,
  `docs/VAPI.md`, `docs/PAYMENTS.md`, `docs/SECURITY.md`,
  `docs/BOOKING_FLOW.md`, `docs/AIRLINE_PROVIDER.md` — all already
  current or correctly frozen; no drift found in any of them.
- **No source code was changed.** The one item that looked like it might
  need a code fix (§6.3, `customers.email`) turned out, on inspection, to
  already be correct.
