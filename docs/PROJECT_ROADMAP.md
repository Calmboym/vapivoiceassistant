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
| 4 | Authentication, RBAC, audit logging, rate limiting, security | 🟢 **Complete, core logic executed; HTTP layer written, unexecuted** | 93 dependency-free tests (`test_security_core.py`) actually pass (re-run this audit: confirmed); `tests/test_api_security.py` (6 classes, 18 methods) written against real FastAPI `TestClient`, skips cleanly here | Install FastAPI/SQLAlchemy/pytest in a networked environment and run `test_api_security.py` for real — the single highest-leverage unblocked action for the whole project (blocks verifying Phases 4 through 7's HTTP layers all at once) |
| 5 | Vapi integration: webhook, tools, assistant config, voice system prompt | 🟢 **Complete as code; live-call behavior unverified** | `app/api/routes/vapi.py`, `app/core/vapi/*`, `app/core/security/vapi_{authorization,webhook_auth}.py`; 56 dependency-free tests pass; tool-schema ⇄ authorization-matrix ⇄ dispatch-table consistency independently re-verified this audit (21 schemas, 23 matrix entries, 16 wired dispatch functions — see §6.4 for tools present in spec §19 but absent here) | Live Vapi account + real phone call; `transfer_to_human`'s native `transferCall` companion tool has never been configured. **Updated 2026-09-09 (T-4):** `scripts/setup_vapi.py` (spec §51) is now written (24 dependency-free tests, `OK`) and would automate the `transferCall` configuration too — but has never been run against a real account, so this row's "live-call behavior unverified" still stands unchanged. |
| 6 | Phone integration: inbound call, voice booking/lookup/cancellation, human transfer | 🟡 **PARTIAL — and the repo's own phase labels do not match this row; read §6.1 before trusting any doc that says "Phase 6" without qualification** | The *logic* for voice booking/lookup/cancellation/human-transfer-logging is the same code delivered under "Phase 5" above (`create_booking`/`get_booking`/`cancel_booking`/`modify_booking`/`transfer_to_human` Vapi tools). What has **not** happened: a real phone number connected to a real Vapi assistant, or a real inbound call ever reaching it. **Updated 2026-09-09 (T-4, authorized this session):** `scripts/setup_vapi.py` now exists — written, 24 dependency-free tests passing, never run against a real account | Live phone number + inbound call test (Master Build Prompt §79 items 19–25); running `scripts/setup_vapi.py --apply` against a real Vapi account for the first time; native `transferCall` tool configuration (the script automates creating it, but the transfer itself needs a real call to confirm) |
| 7 | Payments: Stripe, webhooks, booking/payment consistency | 🟡 **PARTIAL — delivered under the repo's own "Phase 6 Milestone 1" label; see §6.1. `refund_payment` (T-3) closed one of the two gaps this row used to list** | `create_payment_session`/`get_payment_status`/`refund_payment` implemented, code-reviewed, and (for the dependency-free portions) executed — 46 tests in `test_payments_core.py`; `CancellationService.cancel()` now calls the real provider for a paid cancellation (`docs/PAYMENTS.md` §9); `StripePaymentProvider` (incl. `refund_payment`) written and cross-checked against live Stripe docs but never executed (no network in any sandbox to date) | A real Stripe test-mode Checkout Session AND a real test-mode refund completing end-to-end; a `refund.updated`/`charge.refunded` webhook subscription (a non-instant refund's `pending`/`requires_action` status never auto-resolves — scoped out of T-3 on purpose); out-of-band delivery of the payment link (no email/SMS provider exists — see Phase 8) |
| 8 | Notifications: email, SMS | 🔴 **NOT IMPLEMENTED** | Only `app/services/email_provider.py::MockEmailProvider` exists (not a real delivery mechanism); no SMS provider anywhere in the codebase; `RESEND_API_KEY`/`TWILIO_*` are defined in `Settings` and `.env.example` but nothing reads them | Build a real email provider (Resend or SMTP) and an SMS provider (Twilio), wire booking-confirmation and payment-link delivery to them |
| 9 | Admin dashboard | 🔴 **NOT IMPLEMENTED** | No `/api/v1/admin`, `/api/v1/customers`, or `/api/v1/calls` routes exist (confirmed by reading every route file and `main.py`'s router registration); no admin pages in `apps/web`; only the backend RBAC boundary (`ADMIN`/`SUPER_ADMIN` roles, `admin.*` permissions) and `bootstrap_admin.py` exist | Everything — API routes to read `Call`/`ToolExecution`/`Booking`/`Payment` data for staff, and the Next.js admin UI itself |
| 10 | Testing & production hardening | 🟡 **PARTIAL** | **236/236 dependency-free tests pass — re-executed and confirmed this session (2026-09-08, T-3: +13 over the prior 223, all in `test_payments_core.py` for `refund_payment`).** `tests/test_api_security.py` and `tests/test_vapi_api.py` are written (8 skips, confirmed) but have never run against real FastAPI. `tests/{e2e,integration,voice}/` contain only `README.md` placeholders — no Playwright, no real-DB integration tests, no voice conversation test suite (spec §56) exist yet | Install the full stack and run the FastAPI-level suites for real; write the Playwright E2E suite (needs real booking pages in `apps/web` first — those don't exist either, see Phase 9); write the voice conversation test suite from spec §56 |

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
- `get_customer`/`create_customer`/`update_customer` — no
  `/api/v1/customers` route family exists at all (Phase 9 territory);
  today a `Customer` row is only ever created implicitly, inside
  `create_booking`, per `docs/SECURITY.md` §3's documented design. A
  standalone customer-facing tool has no backing service to call yet.
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
         payments, analytics) + Next.js admin UI
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
- **This session's work (2026-09-09):** T-4 (Phase 6 remainder —
  telephony) moved from Proposed to **AUTHORIZED** on the project
  owner's explicit instruction, and `scripts/setup_vapi.py` (spec §51,
  WBS-2.1) was written — idempotent create-or-update for the 21
  registered Vapi tools, the native `transferCall` tool, the Assistant,
  and phone-number attachment, cross-checked against Vapi's current API
  docs (fetched this session; includes one genuinely new finding —
  Vapi's move to a dashboard-managed Custom Credentials webhook-auth
  system, which does not contradict what
  `vapi_webhook_auth.py` already had on record). 24 new dependency-free
  tests (`scripts/test_setup_vapi.py`), executed: `OK`. **T-4 is NOT
  closed** — see its `docs/TASK_BOARD.md` entry: WBS-2.2 through 2.5 (a
  real phone number, a real inbound call, live `transferCall`
  verification) remain BLOCKED on the same external dependency (a live
  Vapi account) the task always named, compounded by this sandbox's
  network restriction.
- **Current authorized work:** T-1 (install & execute the FastAPI/
  SQLAlchemy test layer for real) remains authorized and still
  **BLOCKED** — re-confirmed again this session (`python3 -c "import
  fastapi"` / `sqlalchemy` / `stripe` / `httpx` / `pydantic` all raise
  `ModuleNotFoundError`; network still disabled in this sandbox).
  Identical to every prior sandbox since Phase 4; not a new finding. T-4
  is now also authorized and also **BLOCKED**, for the same underlying
  reason plus its own further dependency on a live Vapi account — see
  `docs/TASK_BOARD.md`'s T-1 and T-4 entries for the full attempt logs.
- **Next work (candidates, not yet chosen):** Step 1 (get the full stack
  installed and run the HTTP-level test suites for real) is the
  recommended first move regardless of which feature comes next, because
  every remaining phase's HTTP layer is equally unverified and this is
  the cheapest way to convert "written, reviewed" into "known to work" or
  "found a real bug" across all of them at once — this now includes
  T-3's `refund_payment` route/service/CancellationService changes too.
  Running `scripts/setup_vapi.py --apply` for the first time, against a
  real Vapi account, is the equivalent next move for T-4.
- **Blocked work:** anything requiring network access this build
  environment doesn't have (installing FastAPI/SQLAlchemy/`stripe`/
  `httpx`, `docker compose up`, a live Vapi account, a live Stripe
  test-mode account) — confirmed still blocked this session too (`pip
  install fastapi` fails here exactly as it has since Phase 4).
- **Important known risks:** (1) the Phase 6/7 numbering question in
  §6.1 is unresolved and should be decided explicitly rather than left
  ambiguous going forward; (2) ~~`CancellationService.cancel()` flips
  `payment_status` to `REFUNDED` without ever calling `PaymentProvider`~~
  — **fixed in T-3** (docs/PAYMENTS.md §9); a related, narrower gap
  remains in its place: no webhook subscription for Stripe's
  `refund.updated`/`charge.refunded` events, so a non-instant
  (`pending`/`requires_action`) refund never auto-resolves on its own —
  deliberately out of T-3's scope, see `docs/PAYMENTS.md` §9's last
  bullet; (3) the audit-log actor-spoofing gap in §6.6.

## 9. Known gaps and risks

**Missing features (by original phase):**
- Phase 6: live telephony connection (a real number, a real inbound
  call), native `transferCall` verification against a real call.
  **Updated 2026-09-09 (T-4):** `scripts/setup_vapi.py` itself is now
  written — see below, no longer listed as missing, only as unexecuted.
- Phase 7: payment-link delivery. (`refund_payment` closed by T-3,
  2026-09-08.)
- Phase 8: real email provider, real SMS provider — entirely absent.
- Phase 9: admin dashboard — entirely absent (no routes, no UI).
- Phase 10: Playwright E2E, voice conversation test suite — entirely
  absent (placeholders only).
- Cross-cutting domain gaps: seat selection/seat map, baggage mutation,
  support tickets, callback requests, FAQ/knowledge base, i18n (German/
  Persian per spec §41), GDPR export/deletion endpoints, call recording/
  transcription, retention-policy enforcement jobs (variables exist,
  nothing reads them).
- Newly identified this audit (§6.4): `update_passenger`, `get_customer`/
  `create_customer`/`update_customer`, `end_call`, `get_airport`/
  `search_airports`, `get_faq` — no Vapi tool registered at all, not even
  as a placeholder.

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
