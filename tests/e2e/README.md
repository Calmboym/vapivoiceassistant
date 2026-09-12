# tests/e2e

Reserved for Playwright end-to-end tests against the running web + api
stack. Two halves, in very different states as of T-7
(docs/TASK_BOARD.md, WBS-6.1):

- **`admin/`** — a real, written suite covering the staff-facing admin
  dashboard (Phase 9 / T-6): dashboard, bookings/customers/calls list +
  detail pages, and the login redirect gate. WRITTEN, NEVER EXECUTED (no
  Node network access in this sandbox, no live stack to point it at) —
  see `admin/README.md` for how to actually run it and for a real bug
  (`/login`'s `next=` param being ignored) this task found and fixed
  while writing it.
- **The customer-facing flow** (search -> book -> lookup -> cancel ->
  modify -> human transfer) — still not started, and can't be: no such
  pages exist in `apps/web/app/` yet (only `account/`, `admin/`,
  `login/`, `register/`, and a status `page.tsx`). This is the same gap
  WBS-6.1 already flagged as an open sequencing question ("whether that's
  its own small task or folds into WBS-6 itself"); T-7 did not resolve it
  by building a customer booking UI as an unauthorized scope expansion.
  See docs/handoffs/2026-09-12-t7-testing-hardening.md.
