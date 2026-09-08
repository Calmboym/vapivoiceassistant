# Handoff: T-3 — Phase 7 remainder: `refund_payment`

## 1. Current project position

Phases 1–5 complete. Phase 7 Milestone 1 (Stripe Checkout Sessions —
`create_payment_session`/`get_payment_status`) complete as of
2026-09-06. This session (2026-09-08) closes the two code items of
WBS-3 (`docs/WORK_BREAKDOWN_STRUCTURE.md`): `refund_payment` itself, and
wiring `CancellationService.cancel()` to actually call it. T-1 (install
and execute the FastAPI/SQLAlchemy stack for real) remains authorized
and still BLOCKED in every sandbox used on this project to date,
including this one — re-confirmed again this session (see §11).

## 2. Completed work

- `PaymentProvider.refund_payment()` — new abstract method, implemented
  in both `MockPaymentProvider` and `StripePaymentProvider`.
- `RefundResult`/`RefundStatus`/`PaymentRefundError` — new types in
  `app/providers/payments/base.py`, mirroring `CheckoutSession`/
  `CheckoutSessionStatus`/`PaymentSessionCreationError`'s existing roles
  for session creation.
- `Payment` model gained five refund-tracking columns
  (`provider_refund_id`/`refunded_amount`/`refund_status`/
  `refunded_at`/`refund_reason`) via migration `0005`. **`Payment.status`
  itself was deliberately left untouched** — see §5 for why this was the
  single most important design decision this session.
- `PaymentService.apply_refund_outcome()` (shared, non-committing —
  mutates `Payment`/`Booking` fields and writes one audit event only)
  and `PaymentService.refund_payment()` (staff-facing, owns its own
  commit/rollback/idempotency-store transaction — the entry point for
  the new REST route).
- `CancellationService.cancel()` now takes a 4th constructor argument
  (`payment_provider: PaymentProvider`) and, for a `PAID` booking, calls
  the provider directly for the airline's fee-adjusted
  `refundable_amount`, using `apply_refund_outcome()` — but never
  `PaymentService.refund_payment()`'s own commit/rollback (see §5). All
  4 existing `CancellationService(...)` call sites
  (`app/api/routes/bookings.py` x2, `app/api/routes/vapi.py` x2) updated
  to pass `get_payment_provider()`.
- `POST /api/v1/payments/refunds` — new staff-only REST route in
  `app/api/routes/payments.py`, gated by `require_payment_access(...,
  required_permission=Permission.PAYMENTS_REFUND.value)` — the identical
  gate shape as the other two payment routes. `RefundCreateRequest`
  requires an explicit `confirmed: true` field, mirroring the
  `customer_confirmed` pattern used elsewhere for MASTER_RULES §3's
  explicit-confirmation principle.
- `_PAYMENT_PROVIDER_ERROR_HTTP_STATUS["PAYMENT_REFUND_FAILED"] = 502`
  added to `app/core/exceptions.py`.
- 13 new dependency-free tests in `tests/test_payments_core.py`
  (`PaymentProviderErrorTests` +2, new `RefundResultTests` (3), new
  `MockPaymentProviderRefundTests` (8)) — full/partial/idempotent-replay/
  over-refund/unpaid-session/unknown-payment-intent/wrong-lookup-key
  cases, all executed and passing.
- Documentation updated: `docs/TASK_BOARD.md` (T-3 authorized and marked
  done with full scope notes), `docs/PAYMENTS.md` (§6, §9 rewritten from
  "known limitation" to "fixed," §12, §13), `docs/PROJECT_STATE.md`,
  `docs/PROJECT_ROADMAP.md` (§5 row 7/10, §8 Current Position),
  `docs/WORK_BREAKDOWN_STRUCTURE.md` (WBS-3.1/3.2 marked done),
  `docs/PRODUCTION_CHECKLIST.md` (items 12, 15, 60, the "out of scope"
  list), `docs/ARCHITECTURE.md`, `README.md` (test count, status line,
  "What's next").

## 3. Files created

- `apps/api/app/db/migrations/versions/0005_add_payment_refund_columns.py`
- `docs/handoffs/2026-09-08-t3-refund-payment.md` (this file)

## 4. Files modified

- `apps/api/app/providers/payments/base.py`
- `apps/api/app/providers/payments/mock.py`
- `apps/api/app/providers/payments/stripe_provider.py`
- `apps/api/app/models/payment.py`
- `apps/api/app/schemas/payment.py`
- `apps/api/app/services/payment_service.py`
- `apps/api/app/services/cancellation_service.py`
- `apps/api/app/api/routes/payments.py`
- `apps/api/app/api/routes/bookings.py` (import + 2 call sites)
- `apps/api/app/api/routes/vapi.py` (2 call sites)
- `apps/api/app/core/exceptions.py`
- `apps/api/tests/test_payments_core.py`
- `docs/TASK_BOARD.md`, `docs/PAYMENTS.md`, `docs/PROJECT_STATE.md`,
  `docs/PROJECT_ROADMAP.md`, `docs/WORK_BREAKDOWN_STRUCTURE.md`,
  `docs/PRODUCTION_CHECKLIST.md`, `docs/ARCHITECTURE.md`, `README.md`

## 5. Architecture changes

**The one decision worth a new session's full attention:** `Payment.
status` was deliberately NOT extended with a `"REFUNDED"` value.
`app/core/payments/state_machine.py` was not touched at all. A refund is
modeled as five new, orthogonal columns on `Payment` — the Checkout
Session's own status stays `"SUCCEEDED"` forever once paid; a refund is
a separate fact layered on top (mirrors how Stripe itself keeps
`PaymentIntent.status` and a distinct `Refund` object, rather than
mutating the PaymentIntent's status). `Booking.payment_status` (a plain
string field, not state-machine-governed) is still what flips to the
pre-existing `"REFUNDED"` value — set by `PaymentService.refund_payment`
(only once the cumulative refund covers the full amount) or
`CancellationService.cancel` (always, on a successful paid
cancellation — full or fee-adjusted).

This was not the first design considered. Adding `"REFUNDED"` to
`PAYMENT_SESSION_STATUSES`/`_ALLOWED_TRANSITIONS`/
`BOOKING_PAYMENT_STATUS_FOR_SESSION` was the initial plan and would have
been a smaller diff — but it directly breaks an existing, currently-
passing test: `tests.test_payments_core.StateMachineTests.
test_booking_payment_status_mapping_never_produces_refunded`, which
explicitly asserts `"REFUNDED" not in BOOKING_PAYMENT_STATUS_FOR_SESSION.
values()`. Re-reading that test's own reasoning (and
`state_machine.py`'s docstring, which already said "that value stays
CancellationService's alone") confirmed the ORIGINAL design intent was
exactly what this session's approach preserves — the test wasn't
encoding an oversight to override, it was encoding the correct boundary.
**If a future session is tempted to add a payment-session `"REFUNDED"`
status, re-read that test and this section first.**

**Second architectural point:** `CancellationService` now constructs its
own internal `PaymentService(db, payment_provider, idempotency)` (same
`db`/`idempotency` it already had) purely to reuse `PaymentService.
payments` (a `PaymentRepository`) and `apply_refund_outcome()`. It never
calls `PaymentService.refund_payment()` — that method owns its own
`db.commit()`/`db.rollback()`, and nesting two commit/rollback owners on
one shared SQLAlchemy `Session` would let a failed nested rollback erase
the outer, already-true "the airline cancelled this booking" state
(`apply_refund_outcome()` itself never calls commit/rollback — see its
docstring). This is the first place in the codebase where one service
composes with another; it was judged consistent with, not a departure
from, `PaymentService`'s own docstring ("the ONE place payment business
logic lives") — the alternative (duplicating the outcome-mutation logic
inside `CancellationService`) would have violated that principle instead.

## 6. Database changes

Migration `0005` (`down_revision = "0004"`): adds
`provider_refund_id` (indexed), `refunded_amount`, `refund_status`,
`refunded_at`, `refund_reason` to `payments`. No changes to any existing
column, index, or constraint. Not applied to any real database — no
Postgres available in this sandbox (see §11).

## 7. API changes

New: `POST /api/v1/payments/refunds` — staff/finance-only
(`PAYMENTS_REFUND`). Request: `{pnr, idempotency_key, confirmed, amount?,
reason?}`. Response: `{payment_id, pnr, payment_status,
booking_payment_status, refund_status, refunded_amount, currency,
provider_refund_id}`. No Vapi tool equivalent exists or is planned — see
§9.

## 8. Integration changes

`StripePaymentProvider.refund_payment()` calls `stripe.Refund.create`
against `payment_intent` (not `charge`), cross-checked against
docs.stripe.com/api/refunds/create and .../refunds/object (fetched this
session, not assumed from training data): optional integer `amount` for
a partial refund, `reason` restricted to `duplicate`/`fraudulent`/
`requested_by_customer` (omitted from the request entirely when not
set — not passed as `reason=None`, since this codebase's own rule is to
never assume undocumented SDK kwarg-filtering behavior). `Refund.status`
(`pending`/`requires_action`/`succeeded`/`failed`/`canceled`) is
returned as-is via `RefundStatus`, with an unrecognized value falling
back to `PENDING` (never silently treated as `SUCCEEDED`).

## 9. Security changes

None to the authorization primitives themselves — `authorize_payment_
access()`, `require_payment_access()`, and `RBAC`'s `PAYMENTS_REFUND`
permission were all already correct (see the pre-existing, unmodified
test `tests.test_security_core.OwnershipTests.
test_finance_role_can_refund_anyone`, re-confirmed passing this
session). T-3 only added the route that finally exercises that
already-correct policy. Confirmed `refund_payment` correctly stays OUT
of `TOOL_AUTHORIZATION_MATRIX`'s Vapi-schema surface — no new schema was
added to `app/core/vapi/tool_schemas.py`, and the pre-existing test
`tests.test_vapi_core.ToolRegistryConsistencyTests.
test_authorization_entries_without_a_schema_are_exactly_staff_only`
(unmodified) still passes, which is the thing that would have caught a
mistaken addition.

## 10. Tests executed — exact results

```
cd apps/api && python3 -m unittest tests.test_core_logic \
  tests.test_security_core tests.test_vapi_core tests.test_payments_core \
  tests.test_api_security tests.test_vapi_api -v
```
→ **`Ran 236 tests in 0.209s` — `OK (skipped=8)`.** Zero failures, zero
errors. The 8 skips are the same pre-existing FastAPI-dependent test
classes (`test_api_security.py` ×6 classes, `test_vapi_api.py` ×2
classes) — unrelated to this session, confirmed still skipping for the
same reason (`ModuleNotFoundError: No module named 'fastapi'`), not a
new or different skip.

Breakdown for `test_payments_core.py` specifically: 46 tests (was 33
before this session) — `StateMachineTests` (8, unchanged),
`WebhookEventMappingTests` (7, unchanged), `MockPaymentProviderTests`
(14, unchanged), `PaymentProviderErrorTests` (6 — was 4, +2 this
session), `RefundResultTests` (3, new this session),
`MockPaymentProviderRefundTests` (8, new this session).

Before writing the formal tests, `MockPaymentProvider.refund_payment`
was exercised manually via a throwaway script (full refund, idempotent
replay, over-refund, unknown-payment-intent, unpaid-but-known-session,
two-partials-summing-exactly, post-full-refund-rejection,
wrong-lookup-key) to confirm the logic before committing to test
assertions — all matched expected behavior on the first attempt after
one signature-name correction (`reference=` not `booking_pnr=`, caught
by `TypeError` on the first run).

Also re-confirmed this session, unprompted, exactly as done for T-1 and
Milestone 1: `python3 -c "import fastapi"` / `sqlalchemy` / `stripe` all
raise `ModuleNotFoundError` in this sandbox. Not a new finding.

## 11. Runtime verification status

Per `docs/PAYMENTS.md` §12 (updated this session) — the honest,
component-by-component breakdown lives there and is not duplicated here
in full. Summary: everything touching only `app/providers/payments/
{base,mock}.py` is **Verified locally** (executed, 236/236 passing).
Everything touching `app/models/payment.py`, migration `0005`,
`app/services/payment_service.py`, `app/services/cancellation_service.
py`, `app/api/routes/payments.py`, `bookings.py`, or `vapi.py` is
**Written, reviewed, not executed** — needs SQLAlchemy/FastAPI, neither
installable here. `StripePaymentProvider.refund_payment` is **Written,
cross-checked against current Stripe documentation, not executed** —
needs `stripe`, also not installable here, and ultimately needs a real
Stripe test-mode account regardless of sandbox.

## 12. Known limitations (this session)

- No webhook subscription for Stripe's `refund.updated`/
  `charge.refunded` events. A refund that comes back `pending`/
  `requires_action` from the synchronous `POST /v1/refunds` call is
  recorded as such (`Payment.refund_status`) but nothing resolves it to
  `succeeded`/`failed` later on its own. Explicitly out of T-3's scope
  (`docs/TASK_BOARD.md`) — a future milestone would add a `refund.*`
  case to `PaymentProvider.verify_and_parse_webhook`/`PaymentService.
  handle_webhook_event`, mirroring `checkout.session.completed`.
- If `CancellationService.cancel()`'s refund call to the provider fails
  (a real `PaymentProviderError`, e.g. Stripe outage), the airline
  cancellation is NOT rolled back (already happened, can't be undone
  locally) — `Booking.payment_status` deliberately stays `"PAID"`, an
  audit event records the failure, and the standalone `POST /refunds`
  route is the intended manual recovery path. This fallback path itself
  is written and reviewed but, like everything else needing SQLAlchemy,
  has never actually run.
- No test exists (and none can, in this sandbox) that exercises
  `PaymentService.refund_payment` or `CancellationService.cancel`'s new
  branch end-to-end against a real database — the dependency-free tests
  only reach as far as `MockPaymentProvider.refund_payment` itself.

## 13. Blocked items

Same as every session since Phase 4: T-1 (install and run FastAPI/
SQLAlchemy for real) — network access to PyPI is unavailable in this
sandbox (`403 host_not_allowed` on the egress proxy for `pypi.org`, no
`docker` binary, no offline wheel cache). Re-confirmed again this
session; not a new finding.

## 14. Deferred items (explicitly out of this session's scope)

- WBS-3.3 (a real Stripe test-mode Checkout Session AND a real test-mode
  refund, completed end-to-end) — needs T-1's environment plus a live
  Stripe test-mode account.
- WBS-3.4 (PCI-relevant Stripe Dashboard configuration review) — a human
  task, not code.
- The `refund.updated`/`charge.refunded` webhook subscription (§12
  above) — deliberately scoped out, not silently dropped.
- Payment-link delivery (WBS-4, Phase 8) — untouched, unrelated to T-3.

## 15. Pre-existing issues discovered but NOT fixed (out of authorized scope)

- `docs/PROJECT_STATE.md` (33) and `docs/PROJECT_ROADMAP.md` (44)
  disagreed with each other about `test_payments_core.py`'s pre-T-3 test
  count before this session touched either file. Neither matched the
  other. Both are now superseded by the actual, freshly re-run count
  (46) and have been corrected to agree — but the fact that two
  "canonical" docs had silently drifted from each other, undetected
  until this session happened to need the exact number, is itself worth
  a future session's attention: it suggests these per-file counts get
  hand-typed rather than generated, which is exactly the kind of thing
  that drifts quietly. Not fixed beyond correcting the two instances
  found; no broader audit of every count in every doc was performed
  (that would be its own task, not part of T-3's authorized scope).
- Several internal cross-references inside `docs/PRODUCTION_CHECKLIST.md`
  pointed at the wrong item number (e.g. item 15 said "see item 56" when
  it meant item 60; item 12 said "see item 56 below" for the same
  reason). Corrected the two instances touched by this session's edits;
  did not audit the rest of the file's cross-references.

## 16. Remaining work within the project

Per `docs/PROJECT_ROADMAP.md` §8 (updated this session) and
`docs/TASK_BOARD.md`: T-1 (blocked), T-2 (Phase 6/7 numbering decision,
proposed), T-4 (telephony), T-5 (notifications), T-6 (admin dashboard),
T-7 (testing/hardening), T-8 (this audit's newly-found gaps). None of
these were touched by T-3.

## 17. Recommended next step

Unchanged from every prior handoff's recommendation: get the full stack
installed and the FastAPI-level suites running for real, in an
environment with actual network access. This is now slightly more
valuable than before T-3, since it would also be the first real
execution of everything in §11's "Written, reviewed, not executed" list —
including a chance to actually exercise `CancellationService.cancel()`'s
new refund-failure-doesn't-roll-back-the-cancellation branch, which is
exactly the kind of subtle, session-boundary logic this project's own
bug history (IDOR, mutable-dataclass-aliasing, etc.) suggests is worth
distrusting until proven.

## 18. Anything the next session must know

Read §5 above before touching `app/core/payments/state_machine.py` or
adding any new `Payment.status` value for any reason — the reasoning
there is why refunds were deliberately NOT modeled as a session-status
transition, and re-deciding that without re-reading it risks quietly
reintroducing the exact assumption `test_booking_payment_status_mapping_
never_produces_refunded` was written to prevent.
