# Handoff: T-6 — Phase 9: admin dashboard

## 1. Current project position

Phases 1–5 complete (repo/infra, DB schema + mock provider, core booking
flows, authentication/RBAC/security, Vapi voice integration). Phase 7
Milestone 1 (Stripe payment sessions) complete. T-3 (`refund_payment`)
complete. T-4 (`scripts/setup_vapi.py`) written, never run against a
live account. T-5 (Phase 8 — real email/SMS providers) complete,
unexecuted pending network egress + credentials. This session: T-6
(Phase 9 — admin dashboard), moved from Proposed to AUTHORIZED on the
project owner's explicit instruction ("Execute and authorize T-6"), same
mechanism T-4/T-5 used. Read `docs/PROJECT_ROADMAP.md` §8 and
`docs/TASK_BOARD.md`'s T-6 entry for the full reconciled account this
handoff summarizes.

## 2. Completed work

- A new authorization primitive, `authorize_staff_access()` (`app/core/
  security/ownership.py`) + `require_staff_permission()` (`app/api/
  deps_auth.py`), for admin-wide LIST endpoints that have no single
  resource owner to compare against (list-every-customer, in practice —
  see §9 below for why the calls/admin routes didn't need it).
- Repository read/list/count methods added to `customer_repository.py`,
  `call_repository.py`, `tool_execution_repository.py`,
  `booking_repository.py`, `payment_repository.py`; a new
  `audit_log_repository.py` — that table's first reader anywhere in the
  codebase (it has had a writer, `record_audit_event()`, since Phase 4).
- A new, dependency-free `app/core/admin/analytics.py` — booking-status
  breakdown, payment-conversion rate, cancellation rate, gross/net
  revenue by currency, daily revenue points. Deliberately does NOT
  compute a "quote conversion rate" — see §12 below.
- Three new services (`customer_service.py`, `call_service.py`,
  `admin_service.py`), three new schema modules (`schemas/{customer,
  call,admin}.py`), three new route modules (`api/routes/{customers,
  calls,admin}.py`), registered in `main.py`.
- Seven Next.js pages under `apps/web/app/admin/` plus a staff-gated
  layout, a new `components/admin/` directory (this app's first), a new
  `lib/adminTypes.ts`, and small extensions to `lib/api.ts`
  (`patch()`) and `middleware.ts` (`/admin` added to the UX-only route
  guard).
- 22 new dependency-free tests: 8 in a new `StaffAccessTests` class plus
  1 new `RbacTests` test in `tests/test_security_core.py`; 13 in a new
  `tests/test_admin_core.py`. **289/289 dependency-free tests pass**,
  re-executed and confirmed this session.
- Full documentation sweep: `TASK_BOARD.md`, `PROJECT_STATE.md`,
  `PROJECT_ROADMAP.md`, `WORK_BREAKDOWN_STRUCTURE.md`, `MASTER_RULES.md`
  §7, `.github/workflows/t1-verify.yml`, `README.md`,
  `PRODUCTION_CHECKLIST.md` — all updated to reflect what changed.

## 3. Files created

Backend (`apps/api/app/`):
- `core/admin/__init__.py`, `core/admin/analytics.py`
- `repositories/audit_log_repository.py`
- `services/customer_service.py`, `services/call_service.py`,
  `services/admin_service.py`
- `schemas/customer.py`, `schemas/call.py`, `schemas/admin.py`
- `api/routes/customers.py`, `api/routes/calls.py`,
  `api/routes/admin.py`

Backend tests (`apps/api/tests/`):
- `test_admin_core.py` (13 tests)

Frontend (`apps/web/`):
- `lib/adminTypes.ts`
- `components/admin/StatusBadge.tsx`, `components/admin/Pagination.tsx`,
  `components/admin/ErrorNotice.tsx`
- `app/admin/layout.tsx`, `app/admin/page.tsx`
- `app/admin/bookings/page.tsx`, `app/admin/bookings/[id]/page.tsx`
- `app/admin/customers/page.tsx`, `app/admin/customers/[id]/page.tsx`
- `app/admin/calls/page.tsx`, `app/admin/calls/[id]/page.tsx`

Docs:
- `docs/handoffs/2026-09-11-t6-admin-dashboard.md` (this file)

## 4. Files modified

Backend:
- `app/core/security/ownership.py` — added `authorize_staff_access()`.
- `app/api/deps_auth.py` — added `require_staff_permission()`.
- `app/repositories/customer_repository.py` — `get_by_id`, `list_admin`,
  `count_admin`.
- `app/repositories/call_repository.py` — `get_by_id`, `list_admin`,
  `count_admin`.
- `app/repositories/tool_execution_repository.py` — `list_for_call`.
- `app/repositories/booking_repository.py` — `get_by_id`, `list_admin`,
  `count_admin`, `list_for_analytics`.
- `app/repositories/payment_repository.py` — `list_succeeded_since`.
- `app/schemas/common.py` — `PageMeta`/`make_page_meta()` (new
  pagination convention; none existed before this task).
- `app/main.py` — registered the three new routers.

Backend tests:
- `apps/api/tests/test_security_core.py` — new `StaffAccessTests` class
  (8 tests), one new `RbacTests` test
  (`test_customer_role_never_holds_admin_or_calls_permissions`).

Frontend:
- `apps/web/lib/api.ts` — added `api.patch()`.
- `apps/web/middleware.ts` — added `/admin` to `PROTECTED_PREFIXES` and
  the matcher.

Docs: `docs/TASK_BOARD.md`, `docs/PROJECT_STATE.md`,
`docs/PROJECT_ROADMAP.md`, `docs/WORK_BREAKDOWN_STRUCTURE.md`,
`docs/MASTER_RULES.md`, `.github/workflows/t1-verify.yml`, `README.md`,
`docs/PRODUCTION_CHECKLIST.md`.

## 5. Architecture changes

- **New authorization primitive, not a new pattern.** `authorize_staff_
  access()` follows the exact same `AuthDecision`-returning shape every
  other function in `ownership.py` already uses; `require_staff_
  permission()` follows the exact same FastAPI-dependency-factory shape
  `require_permission()`/`require_role()` already use. No new
  architectural concept was introduced — see §9 for exactly why this one
  new function was necessary rather than reusing an existing one.
- **New pagination convention.** `PageMeta`/`make_page_meta()`
  (`app/schemas/common.py`) — the first pagination shape anywhere in
  this codebase, since the one pre-existing list endpoint (`GET
  /bookings/mine`) returns one customer's own bookings, unpaginated,
  because that set is always small. The admin list endpoints are
  genuinely unbounded (every customer, every call, every booking), so
  this is new surface, not an existing convention being followed.
  `limit`/`offset`/`total`/`has_more`, capped at `limit<=100` server-side
  via FastAPI `Query(..., le=100)`.
- **`AdminBookingOut` extends `BookingOut` rather than modifying it.**
  Found during this session: the pre-existing, customer-facing
  `BookingOut` schema has no `id`/`customer_id` field — reasonable for a
  customer viewing their own booking (they don't need their own internal
  UUID), but the admin bookings list/detail views need both, to link to
  a detail page and to filter/group by customer. `AdminBookingOut(
  BookingOut)` adds exactly those three fields (`id`, `customer_id`,
  `customer_email`); none of `BookingOut`'s three existing customer-
  facing callers (`create_booking`/`lookup_booking`/`list_my_bookings`,
  all in `app/api/routes/bookings.py`) changed at all.
- **Passport-masking logic reused, not duplicated.** All three new route
  files that touch booking/passenger data (`customers.py`, `admin.py`)
  call through to `_booking_out()` (and, transitively, its
  `_masked_passport()` helper) already defined in `app/api/routes/
  bookings.py`, rather than re-implementing passenger/passport display —
  one code path for that, not a second one that could drift out of sync.
- **This app's first `components/` directory.** `apps/web/components/
  admin/{StatusBadge,Pagination,ErrorNotice}.tsx` — small, reused across
  all seven admin pages. No new npm dependency was added (network egress
  to npm is blocked in this sandbox regardless, same constraint as
  everything else) — no chart library, react-query stays unused (it was
  already a declared, unused dependency before this session; the admin
  pages use the same `useEffect`+`useState` fetch pattern the rest of
  this app already established, for consistency, not because react-query
  wouldn't have worked).

## 6. Database changes

**None.** No new models, no new migration, no column changes. This
session works entirely on top of existing tables (`Customer`, `Call`,
`ToolExecution`, `Booking`, `Payment`, `AuditLog`) via new
repository/service/schema/route code only.

## 7. API changes

New endpoints, all under `Envelope[T]` (§36's existing response shape):

- `GET /api/v1/customers` — staff-only list (search, `limit`/`offset`).
- `GET /api/v1/customers/{id}` — owner or staff.
- `PATCH /api/v1/customers/{id}` — owner or staff with
  `customers.manage`; contact-info fields only (email/phone/first_name/
  last_name), all optional (PATCH semantics).
- `GET /api/v1/calls` — staff-only list (status filter, pagination).
- `GET /api/v1/calls/{id}` — staff-only detail, including every tool
  execution's redacted arguments.
- `GET /api/v1/admin/bookings` — staff-only list (status/customer_id
  filter, pagination), `admin.read`-gated.
- `GET /api/v1/admin/bookings/{id}` — booking + every payment attempt +
  full audit trail, `admin.read`-gated.
- `GET /api/v1/admin/analytics` — booking/revenue summary, `admin.read`-
  gated.

No existing endpoint's request/response shape changed.

## 8. Integration changes

**None.** No new third-party provider, no new external API. This task
is entirely internal-surface (reading/managing this codebase's own
data), unlike T-4 (Vapi)/T-5 (Resend/Twilio).

## 9. Security changes

- **The IDOR gap this task closes, stated precisely:** `Permission.
  CUSTOMERS_READ` is granted to the bare `CUSTOMER` role (so a customer
  can read their own profile via the pre-existing `authorize_customer_
  profile_access`) AND to every staff role. A naive `require_permission(
  CUSTOMERS_READ)` gate on the new list-ALL-customers endpoint would
  have let that same customer list every OTHER customer's data too — the
  permission alone can't distinguish "read my own profile" from "read
  anyone's profile," because a LIST endpoint has no `target_customer_id`
  to compare against, unlike a single-resource GET. `authorize_staff_
  access()` closes this by additionally requiring `actor.is_staff`
  (§8's own definition: any role other than bare `CUSTOMER`) — see
  `tests/test_security_core.py::StaffAccessTests::
  test_bare_customer_with_the_same_permission_string_denied` for the
  exact scenario this prevents.
- **Confirmed, not assumed, that the other two new route families don't
  need this new primitive.** Grepped `rbac.py`'s `ROLE_PERMISSIONS`: no
  `admin.*` or `calls.*` permission is ever granted to bare `CUSTOMER` —
  pinned in `tests/test_security_core.py::RbacTests::
  test_customer_role_never_holds_admin_or_calls_permissions`. This means
  the pre-existing `require_permission(Permission.ADMIN_READ.value)`/
  `require_permission(Permission.CALLS_READ.value)` are already safe,
  unmodified, for `/api/v1/admin/*`/`/api/v1/calls/*`.
- **Tool-execution arguments are shown to staff, deliberately.**
  `ToolExecution.arguments_redacted` is scrubbed at WRITE time (Phase
  5) — its own model docstring states the goal explicitly: "it should be
  safe to hand a staff member the contents of this table without also
  handing them a live bearer credential." `ToolExecutionOut` trusts that
  write-time guarantee and surfaces the redacted arguments verbatim on
  the call-detail page — this is the redaction's stated purpose, not a
  new risk.
- **No consequential mutation added beyond the one explicit write.**
  `PATCH /api/v1/customers/{id}` (contact-info correction) is the only
  write this task adds; every other new endpoint is read-only. It does
  not touch booking/payment/Vapi business logic (T-6's explicit
  boundary) and goes through the same `require_customer_profile_access`
  ownership check as the pre-existing read path.

## 10. Tests executed — exact results

```
cd apps/api && python3 -m unittest tests.test_core_logic \
  tests.test_security_core tests.test_vapi_core tests.test_payments_core \
  tests.test_notifications_core tests.test_admin_core -v
```
→ `OK`, **289 tests, 0 failures, 0 errors.** 267 pre-existing (T-1
baseline through T-5) + 9 new in `test_security_core.py` + 13 new in
`tests/test_admin_core.py` (new file).

```
cd apps/api && python3 -m unittest tests.test_api_security tests.test_vapi_api -v
```
→ skips cleanly, **8 skipped**, unchanged from before this session — no
regression to the skip behavior itself.

```
cd apps/api && python3 -m py_compile <every .py file under apps/api>
```
→ clean, all 140 files (`app/` + `tests/`), confirmed by direct
execution before writing this handoff, not assumed.

```
cd apps/web && tsc --noEmit --noResolve --ignoreConfig --skipLibCheck \
  --jsx preserve --target es2020 --module esnext \
  --moduleResolution bundler --esModuleInterop \
  <all 10 new/modified .ts/.tsx files>
```
→ **zero `TS1xxx` (genuine syntax) errors.** Remaining diagnostics
(`TS2307`/`TS7026`/`TS7006`/`TS2503`/`TS18046`) are all artifacts of the
missing `node_modules` — cross-checked by running the identical command
against pre-existing, untouched `contexts/AuthContext.tsx` and observing
the same diagnostic classes appear there too, under the same harness.
This is evidence, not proof — see §11 and §12 below for exactly what it
does and doesn't establish.

## 11. Runtime verification status

- **Verified locally, this session:** everything in §10 above.
- **Written, reviewed, NOT executed** (needs SQLAlchemy/FastAPI, not
  installed in this sandbox — same standing constraint as every other
  service/route file in this project since T-1's Attempt log): every
  repository addition, all three new services, all three new route
  files, `app/main.py`'s router registration, `AdminService`'s two
  SQLAlchemy queries that feed `analytics.py` (the pure arithmetic
  itself IS executed — see §10).
- **Written, syntax-checked, NOT type-checked against a real toolchain:**
  all seven Next.js pages, the three new shared components,
  `lib/adminTypes.ts`. `npm install` is blocked in this sandbox (no
  network egress to the npm registry, same constraint documented for
  `pip`/PyPI since T-1) — there is no `node_modules` here to run a real
  `tsc --project tsconfig.json`/`next build` against.
- **Requires external verification / BLOCKED, same class as T-1:**
  - `npm install` in an environment with real network access, then a
    real `tsc --project`/`next build`/`next lint`.
  - `pip install -r requirements.txt` + a real Postgres database, then
    an end-to-end exercise of all seven new HTTP endpoints.
  - A real browser click-through of all seven pages against a running
    backend.

## 12. Known limitations (this session)

- **No "quote conversion rate" analytics metric.** The Master Build
  Prompt's original idea — what fraction of fare quotes become bookings
  — is not computable from what this schema persists today. Confirmed
  by reading `app/services/booking_service.py`: `create_booking()`
  writes `status="CONFIRMED"` directly, and `"QUOTE"` (present in
  `BOOKING_STATUSES`) is never actually written to a stored
  `Booking.status` by any code path — an abandoned fare quote simply
  expires in `FlightService`'s in-memory cache and leaves no row behind.
  `app/core/admin/analytics.py` reports a payment-conversion rate,
  cancellation rate, and gross/net revenue from actually-`SUCCEEDED`
  `Payment` rows instead — see that module's docstring for the full
  reasoning.
- **No standalone "create customer" admin action.** `Customer` rows are
  still only ever created implicitly, inside `create_booking`
  (`CustomerRepository.get_or_create()`, pre-existing). A separate
  staff-initiated "create a customer with no booking" action wasn't an
  identified need and would be new product surface beyond "read-heavy...
  manage surface on top of what exists" (T-6's own scope line).
- **`/api/v1/admin/*` gated on `admin.read` alone.** Per T-6's
  Proposed-section wording (which named `admin.*`/`calls.*`
  permissions specifically, not resource-specific ones), `FINANCE`
  (which holds `bookings.read`/`payments.read` but not `admin.read`)
  cannot reach the admin bookings/analytics views through this route.
  Whether `FINANCE` should reach these views is a product decision this
  session did not make unilaterally — see §16.
- **The `tsc --noResolve` syntax check is evidence, not proof.** It
  cannot catch prop-type mismatches against React/Next's actual type
  definitions, incorrect hook usage that only a real type-checker with
  full library types would flag, or a build-time-only failure. See §11.

## 13. Blocked items

Same class as every prior task in this project:
- `pip install -r requirements.txt` (no network egress in this sandbox).
- `npm install` (no network egress to the npm registry either — the
  first time this specific blocker has mattered for a T-6-sized amount
  of new frontend code; T-4/T-5 didn't touch `apps/web` at all).
- A real Postgres database to run migrations/seed data/the FastAPI layer
  against.

## 14. Deferred items (explicitly out of this session's scope)

- **WBS-5.5** — the Vapi tool schemas for `update_passenger`/
  `get_customer`/`update_customer` etc. Explicitly named as NOT in
  T-6's scope on the task board ("NOT in scope: any change to booking/
  payment/Vapi business logic"). `CustomerService` now exists as the
  backing service those tools would call — this is `T-8`'s scope, now
  unblocked (both of T-8's candidate dependencies, T-4's calls and T-6's
  customers, are done).
- **T-2** (the Phase 6/7 numbering decision) — untouched, unrelated to
  this task.
- **A real chart/graph library for the analytics page** — the overview
  page renders tables and stat cards, not charts; no new npm dependency
  was added this session (see §5).

## 15. Pre-existing issues discovered but NOT fixed (out of authorized scope)

- **`AuditLog.resource_id` inconsistency for booking events.** Confirmed
  by grep: every current `resource="booking"` `record_audit_event()`
  call site (`booking_service.py`/`cancellation_service.py`/
  `passenger_service.py` — all of them, no exceptions) passes
  `resource_id=pnr`, never `resource_id=str(booking.id)`. `AuditLog.
  resource_id` is an unconstrained `String` column with nothing
  enforcing which shape a caller uses. `AdminService.get_booking_
  detail()` works around this defensively — querying both `pnr` and
  `str(booking.id)`, merging, de-duplicating — rather than fixing the
  underlying inconsistency-risk with a data migration normalizing every
  writer onto one shape, which would be a schema/data change outside
  T-6's authorized scope. See that method's docstring for the full
  reasoning, and `docs/TASK_BOARD.md`'s T-6 entry, "Decisions/
  deviations" #3.
- **`Booking.cancellation_deadline` / cabin-class persistence** — both
  found by T-5, still not fixed; unrelated to and unaffected by this
  session's work. Still tracked in `docs/PROJECT_ROADMAP.md` §9.

## 16. Remaining work within the project

1. The `npm install`/`pip install` + real-database items in §11, once
   this project runs somewhere with network egress.
2. A product decision on whether `FINANCE` should reach `/api/v1/admin/
   bookings`/`/api/v1/admin/analytics` (§12) — if yes, that route's
   permission gate needs `Permission.BOOKINGS_READ`/`PAYMENTS_READ`
   added alongside `ADMIN_READ`, a one-line change once decided.
3. T-8 (Vapi tools) and T-2 (Phase 6/7 numbering) remain open.
4. T-1 (install & execute the FastAPI/SQLAlchemy test layer for real)
   remains the single highest-leverage unblocked action for the whole
   project — it would verify Phases 4 through 9's HTTP layers all at
   once, this task's included.

## 17. Recommended next step

Same recommendation as T-3/T-4/T-5's handoffs: get this project running
somewhere with real network access (T-1) — it is the cheapest way to
convert everything in §11's "written, reviewed, NOT executed" bucket
into either "confirmed working" or "found a real bug," across every
phase at once, not just this one. Once that's available, T-8 (Vapi
tools) is the natural next feature-track pick, since both of its
dependencies are now done.

## 18. Anything the next session must know

- **`AdminBookingOut` is the schema to reach for**, not `BookingOut`,
  anywhere staff need a booking's `id`/`customer_id` — see §5. Don't add
  those fields to `BookingOut` directly; that would leak a customer's
  own internal UUID back to themselves for no reason and risks scope
  creep into the customer-facing schema this task deliberately left
  alone.
- **`authorize_staff_access()` is specifically for admin-wide LIST
  endpoints with no single owner to check** — not a general-purpose
  "is this person staff" gate to sprinkle everywhere. A single-resource
  admin GET should keep using `authorize_resource_access`/`authorize_
  customer_profile_access`/`authorize_booking_access`/`authorize_
  payment_access` as appropriate — those already correctly let either
  the owner OR staff through, because they have an actual target id to
  compare against.
- **The `PageMeta` pagination convention is now established** — reuse
  it (`app/schemas/common.py`) for any future list endpoint rather than
  inventing a second shape.
- **This session did not touch `apps/web`'s customer-facing pages at
  all** — the Playwright E2E suite (WBS-6.1) still needs a real
  customer-facing booking UI, which remains unbuilt; the new `/admin`
  section is staff-facing only and doesn't close that gap, though it IS
  now a viable Playwright target in its own right if a staff-facing E2E
  pass is wanted before the customer-facing UI exists.
