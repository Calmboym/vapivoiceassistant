# tests/e2e/admin

T-7 (docs/TASK_BOARD.md, WBS-6.1) — a real Playwright suite for the admin
dashboard (Phase 9 / T-6), covering the staff-facing pages that actually
exist: `/admin` (dashboard), `/admin/bookings`, `/admin/customers`,
`/admin/calls`, and each section's detail page, plus the `/login` ->
`/admin` redirect path.

**WRITTEN, NEVER EXECUTED.** Same honest-labeling discipline as every
other suite in this repo (see docs/PROJECT_STATE.md's Testing table):
this sandbox has no network access, so `npm install` has never run here,
and there is no live web+api+db stack to point it at even if it had.
Every selector was written against the real component source in
`apps/web/app/admin/` and `apps/web/app/login/page.tsx` (headings, table
column text, the search input's placeholder, nav link labels) — nothing
here was guessed or fabricated to fit an assumed UI.

## Running it for real

You need, already running, before `npx playwright test` will do anything
meaningful:

1. The full stack — apps/api + Postgres + Redis — the same one
   `.github/workflows/t1-verify.yml`'s `docker-compose-stack` job brings
   up for WBS-1.
2. `apps/web` running against that API (`npm run dev`, or built+started).
3. A real, already-seeded staff account (any role other than bare
   CUSTOMER) — see `apps/api/app/db/bootstrap_admin.py` or
   `apps/api/app/db/seed.py`.

Then, from this directory:

```
npm install
E2E_STAFF_EMAIL=you@example.com E2E_STAFF_PASSWORD=... \
  BASE_URL=http://localhost:3000 \
  npx playwright test
```

`sections.spec.ts`'s row-click-through tests `test.skip()` themselves
when a table is empty (no bookings/customers/calls yet) rather than
failing — this suite has no seed/fixture step of its own, so it only
asserts what it can about data it doesn't control, and always asserts
the column headers regardless of row count.

## A real bug this task found and fixed while writing these tests

Writing `auth-gate.spec.ts`'s "log in from the /admin redirect" case
surfaced that `apps/web/app/login/page.tsx` was ignoring the `next=`
query parameter `admin/layout.tsx` sends it entirely, and always landing
on `/account` — so a staff member bounced off `/admin` to sign in never
actually got back there without a second manual navigation. Fixed as
part of this task (see that file's own T-7 comment); `auth-gate.spec.ts`
is the regression test for it.

## What this suite does NOT cover, and why

The customer-facing flow the spec's own example scenarios name (search
-> book -> lookup -> cancel -> modify -> human transfer) has no
Playwright coverage here, because it has no pages to test against yet:
`apps/web/app/` has only `account/`, `admin/`, `login/`, `register/`, and
a status `page.tsx` — no search, booking, lookup, cancellation, or
modification screen exists in this codebase. Writing E2E specs against
routes and selectors that don't exist would mean fabricating a UI, which
this task's own instructions (and MASTER_RULES.md's "never fabricate")
rule out. `docs/WORK_BREAKDOWN_STRUCTURE.md`'s WBS-6.1 already flagged
this exact sequencing question as open ("whether that's its own small
task or folds into WBS-6 itself") — see the T-7 handoff
(docs/handoffs/2026-09-12-t7-testing-hardening.md) for why this session
did not resolve that question by building a customer booking UI as an
unauthorized scope expansion, and what building it would take.
