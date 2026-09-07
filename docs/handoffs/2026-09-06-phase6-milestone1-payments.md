# Handoff: Phase 6, Milestone 1 — Payments (Stripe)

**This is a MILESTONE handoff, not a phase handoff.** Phase 6 as a whole
is not complete — only its first milestone (`create_payment_session` +
`get_payment_status`) is. Do not create `PROJECT_HANDOFF_PHASE_6.md` from
this document; that file is reserved for when the entire phase is done,
per this milestone's own authorization (§26: "Do NOT create the final
Phase 6 handoff yet").

Root-level `PROJECT_HANDOFF_PHASE_4.md`/`PROJECT_HANDOFF_PHASE_5.md`
remain the phase-level handoffs. This file lives in `docs/handoffs/`
(a new directory — did not exist before this milestone) specifically to
keep milestone-level handoffs distinct from phase-level ones.

## 1. Current project position

Phases 1–5 complete (see the two root-level phase handoffs).
**Phase 6, Milestone 1 (Payments — Stripe) is complete** to the extent
this sandbox can verify it: every dependency-free component is written
and actually executed; every FastAPI/SQLAlchemy/`stripe`-dependent
component is written and reviewed against verified signatures/
documentation, but not executed (same sandbox constraint — no network
access — that has applied since Phase 4).

**Explicitly authorized scope for this milestone:** `create_payment_session`
and `get_payment_status` only. Nothing else was built. In particular,
NOT built: `refund_payment`, email/SMS delivery of the payment link, seat
selection, support tickets, or any other Phase 6 capability.

## 2. Completed work

- A `Payment` domain model and state machine, independent of any
  particular provider.
- A `PaymentProvider` abstraction with two implementations: a
  deterministic `MockPaymentProvider` (dependency-free, fully tested) and
  a `StripePaymentProvider` (real Stripe Checkout Session integration,
  written and cross-checked against current Stripe documentation, not
  executed).
- A `PaymentService` application service, used identically by both the
  web route and the Vapi voice tools (no duplicated business logic
  between channels).
- Two web routes (create a payment session, check payment status) and a
  Stripe webhook receiver.
- `create_payment_session`/`get_payment_status` flipped from
  `implemented=False` to `implemented=True` in the Vapi tool registry,
  with argument mappers and dispatch functions added — using the
  authorization matrix entries that were **already correct since Phase
  5** (no change needed there).
- Full documentation: `docs/PAYMENTS.md` (new), plus updates to
  `docs/VAPI.md`, `docs/SECURITY.md`, `docs/PRODUCTION_CHECKLIST.md`,
  `docs/ENVIRONMENT_VARIABLES.md`, `README.md`, `.env.example`.

## 3. Files created

```
apps/api/app/core/payments/__init__.py
apps/api/app/core/payments/state_machine.py
apps/api/app/models/payment.py
apps/api/app/db/migrations/versions/0004_add_payments_table.py
apps/api/app/providers/payments/base.py
apps/api/app/providers/payments/mock.py
apps/api/app/providers/payments/stripe_provider.py
apps/api/app/repositories/payment_repository.py
apps/api/app/schemas/payment.py
apps/api/app/services/payment_service.py
apps/api/app/api/routes/payments.py
apps/api/tests/test_payments_core.py
docs/PAYMENTS.md
docs/handoffs/2026-09-06-phase6-milestone1-payments.md   (this file)
```

## 4. Files modified

```
apps/api/app/providers/payments/__init__.py   (was an empty stub; now the provider factory)
apps/api/app/models/__init__.py               (register Payment)
apps/api/app/core/config.py                   (PAYMENT_PROVIDER setting; conditional Stripe validation)
apps/api/app/api/deps.py                      (re-export get_payment_provider)
apps/api/app/main.py                          (wire payments router; log payment_provider)
apps/api/app/core/exceptions.py               (PaymentProviderError -> HTTP handler)
apps/api/app/core/vapi/tool_schemas.py        (implemented=True; customer_confirmed param added)
apps/api/app/core/vapi/argument_mapping.py    (map_create_payment_session, map_get_payment_status)
apps/api/app/api/routes/vapi.py               (two new dispatch fns; _PNR_TOOLS/_DISPATCH entries; except clause)
apps/api/app/core/security/vapi_authorization.py  (comment only — matrix entries themselves unchanged)
apps/api/app/core/security/ownership.py       (docstring only — authorize_payment_access logic unchanged)
apps/api/app/api/deps_auth.py                 (docstring only — require_payment_access logic unchanged)
apps/api/app/services/cancellation_service.py (comment only — documents a known limitation; no behavior change)
apps/api/tests/test_vapi_core.py              (+9 tests, +2 imports)
apps/api/tests/test_security_core.py          (+2 tests)
.env.example                                  (PAYMENT_PROVIDER added)
docs/VAPI.md                                  (tool table, new Payments section, known-limitations annotation)
docs/SECURITY.md                              (new §22)
docs/PRODUCTION_CHECKLIST.md                  (item 15; one "out of scope" sentence)
docs/ENVIRONMENT_VARIABLES.md                 (PAYMENT_PROVIDER row; STRIPE_* row corrected)
README.md                                     (Testing section: command + count, 123 -> 223)
```

No file was deleted. No existing test was altered to make it pass — all
179 pre-existing tests pass unmodified.

## 5. Architecture changes

None to the existing booking/auth/security layers. Additive only:
`PaymentProvider`/`PaymentService`/`Payment` follow the exact same
three-layer shape (provider abstraction -> application service -> route)
`AirlineProvider`/`BookingService`/`Booking` already established. See
`docs/PAYMENTS.md` §1 for the diagram.

One deliberate design resolution worth flagging explicitly: the Vapi path
for these two tools uses the SAME `REQUIRES_VERIFIED_BOOKING`
authorization gate as `cancel_booking`/`modify_booking` (unchanged since
Phase 5), while the web path uses `authorize_payment_access()`
(unchanged since Phase 4, and structurally incapable of accepting a
verification-token actor at all). These are two intentionally different
gates converging on one service, not an inconsistency — full reasoning
in `docs/PAYMENTS.md` §6 and `docs/SECURITY.md` §22.

## 6. Database changes

New table `payments` (migration `0004`, depends on `0003`). Columns,
indexes, and constraints are documented in
`apps/api/app/models/payment.py` and mirrored exactly in the migration —
checked column-by-column against each other manually (no `alembic`
installed to autogenerate/verify — same constraint as migrations
`0001`-`0003`). No existing table's schema changed;
`Booking.payment_status` (pre-existing since Phase 1-3) is now actually
written to for the first time, but its column definition is untouched.

## 7. API changes

New routes: `POST /api/v1/payments/sessions`, `GET
/api/v1/payments/status/{pnr}`, `POST /api/v1/payments/webhooks/stripe`.
No existing route's behavior changed.

## 8. Integration changes

Stripe (via `stripe-python`, already pinned in `requirements.txt` since
before this milestone) is now actually integrated, behind the provider
abstraction — see `docs/PAYMENTS.md` §2 for exactly what was verified
against live documentation versus assumed. No other third-party
integration was touched.

## 9. Security changes

No change to any existing authorization function's *logic* —
`authorize_payment_access()`, `require_payment_access()`, and every entry
in `TOOL_AUTHORIZATION_MATRIX` are byte-for-byte unchanged except for
docstrings/comments. New: `PaymentProviderError` is now caught by
`app/core/exceptions.py`'s handler registry and by `vapi.py`'s except
clause, mapped to safe, user-facing messages (never a raw Stripe
exception). See `docs/SECURITY.md` §22 and `docs/PAYMENTS.md` §6/§7 for
the full reasoning, and item 10 below for the regression test that pins
this design.

## 10. Tests executed — exact results

```
cd apps/api
python3 -m unittest tests.test_core_logic tests.test_security_core tests.test_vapi_core tests.test_payments_core tests.test_api_security tests.test_vapi_api -v
```

```
Ran 223 tests in 0.144s
OK (skipped=8)
```

Breakdown: 179 pre-existing tests (unmodified, still pass) + 44 new —
33 in `tests/test_payments_core.py` (state machine transitions, webhook
event mapping, `PaymentProviderError` hierarchy, `MockPaymentProvider`
including a full create -> simulate-payment -> webhook-parse lifecycle
test), 9 in `tests/test_vapi_core.py` (argument mapping for the two new
tools — confirmation gating, idempotency-key determinism, confirms no
amount field can ever reach the mapped output), 2 in
`tests/test_security_core.py` (pins that `authorize_payment_access` grants
the owner and denies a `VAPI_AGENT`/`ANONYMOUS_VERIFIED` actor for
`payments.create`/`payments.read`, not just the pre-existing
`payments.refund` case). The 8 skips are the same two FastAPI-dependent
files skipping cleanly for the same reason as every prior phase (no
network access to install FastAPI/SQLAlchemy here) — confirmed this
milestone's new imports (`app/api/routes/payments.py`, `app/main.py`
wiring) don't break that clean-skip behavior.

Additional check run: `python3 -m py_compile` against every new/modified
Python file — all compile with no syntax errors. This is a static check,
not execution; it catches syntax errors only, not logic errors that would
only surface at import/runtime with the real dependencies installed.

## 11. Runtime verification status

| Component | Status |
|---|---|
| `app/core/payments/state_machine.py` | ✅ Executed |
| `app/providers/payments/base.py`, `mock.py` | ✅ Executed |
| Two new Vapi argument mappers | ✅ Executed |
| `authorize_payment_access` denial regression | ✅ Executed |
| `app/providers/payments/stripe_provider.py` | 🟡 Written, verified against live Stripe docs, not executed (no network) |
| `Payment` model, migration `0004`, `PaymentRepository`, `PaymentService`, `app/api/routes/payments.py`, `vapi.py`'s two new dispatch functions | 🟡 Written, reviewed against verified signatures, not executed (needs FastAPI/SQLAlchemy/a real Postgres) |
| A real Stripe Checkout Session completing end-to-end | ⬜ Not attempted — needs a live Stripe test-mode account |

Full per-component table with reasoning: `docs/PAYMENTS.md` §12.

## 12. Known limitations (this milestone)

1. **Out-of-band delivery of the payment link is not built.** The tool
   returns the Checkout URL as data; nothing sends it anywhere. No
   real email provider, no SMS provider exists in this codebase.
   Deliberately not built this milestone (explicit instruction: do not
   silently add Resend/Twilio). See `docs/PAYMENTS.md` §8.
2. **Cancellation's refund is local-only.** `CancellationService.cancel()`
   flips `payment_status` to `REFUNDED` without calling Stripe. This was
   pre-existing (Phase 1-3) dead code that is now reachable. Documented
   inline in the code and in `docs/PAYMENTS.md` §9; not fixed (out of
   this milestone's scope — `refund_payment` is a separate, reserved,
   staff-only tool for a future milestone).
3. **Stripe webhook has no rate limiting**, unlike the Vapi webhook.
   Deliberate — reasoning in `docs/PAYMENTS.md` §5.
4. **`StripePaymentProvider` is unexecuted** — see §11 above.
5. **The entire FastAPI/SQLAlchemy layer this milestone added is
   unexecuted** in this sandbox — same constraint as every prior phase.

## 13. Blocked items

- Installing `fastapi`/`sqlalchemy`/`stripe` and running the full test
  suite for real — blocked by this sandbox's lack of network access.
  This has blocked every phase since Phase 4; not new to this milestone.
- A real Stripe test-mode Checkout Session / webhook delivery — blocked
  by the same lack of network access, plus needs an actual Stripe
  account (credentials), which this environment cannot hold either way.
- `docker compose up`, `alembic upgrade head` against a real Postgres —
  same blocker.

## 14. Deferred items (explicitly out of this milestone's scope)

- `refund_payment` (staff/admin-only tool).
- Email/SMS delivery of the payment link.
- Seat selection, support tickets, callback requests — other Phase 6
  candidates, not started.

## 15. Pre-existing issues discovered but NOT fixed (out of authorized scope)

Found while reviewing documentation for accuracy, per this task's
instruction not to silently expand scope to fix unrelated issues.
Recorded here for the next session rather than corrected:

- **`docs/PRODUCTION_CHECKLIST.md` items 16–25** (Vapi webhook/tools/
  Assistant/inbound-call rows) still read "Not started — Phase 5," even
  though Phase 5 completed the Vapi webhook and all 21 tools. This
  checklist was apparently never reconciled with Phase 5's actual
  completion. Only item 15 (Stripe) was touched in this milestone,
  since that's this milestone's own subject.
- **`docs/PRODUCTION_CHECKLIST.md`'s "Explicitly out of scope" section**
  still lists "the Vapi assistant/tools/webhook implementation" as not
  in the tables above — same staleness, same reason not fixed here.
- **`docs/ENVIRONMENT_VARIABLES.md`'s `VAPI_API_KEY` row** still says
  "unused until Phase 5... only the webhook/tool-call code... is still
  Phase 5" — also stale for the same reason. Not touched (out of this
  milestone's scope — it's about Vapi, not Payments).
- **`README.md`'s "Current status" line and "What's next" section, and
  `docs/ARCHITECTURE.md`'s top-level status paragraph** all still say
  "Phases 1–4... The Vapi voice layer... [is] not built yet" — same
  staleness. Not touched: a partial fix (payments only) would leave an
  inconsistent sentence, since the same sentence also misstates the Vapi
  layer's status, which is outside this milestone's authorization.

**Recommended for the next session:** a documentation-accuracy pass
across these Phase-5-era gaps, independent of whatever Phase 6 milestone
comes next.

## 16. Remaining work within the project

- The rest of Phase 6: `refund_payment`, and whichever of seat selection/
  support tickets/callback requests/notifications gets prioritized next.
- The pre-existing Phase 5 documentation staleness noted in §15.
- Everything already listed as not-yet-started in
  `docs/PRODUCTION_CHECKLIST.md` (admin dashboard, i18n, GDPR export/
  deletion, call recording/transcription, Playwright/E2E suites).
- Full-stack runtime verification (§13) once a networked environment is
  available.

## 17. Recommended next step

A real project audit against the original Master Build Prompt, as the
authorizing instruction for this handoff specifies — this document
provides the current, accurate state for that audit to start from,
including the pre-existing staleness in §15 that the audit should decide
how to handle.

## 18. Anything the next session must know

- **Do not re-run Milestone 1's work.** It's done, to the extent stated
  above — verify against this document and the repo, don't rebuild.
- **Two authorization gates for payments is intentional**, not a bug —
  see §5 above before "fixing" it.
- **The `Payment.status` vocabulary (`PENDING`/`PROCESSING`/`SUCCEEDED`/
  `FAILED`/`EXPIRED`/`CANCELED`) is deliberately different from
  `Booking.payment_status` (`UNPAID`/`PENDING`/`PAID`/`REFUNDED`/
  `FAILED`)** — don't conflate them; `BOOKING_PAYMENT_STATUS_FOR_SESSION`
  in `app/core/payments/state_machine.py` is the only translation between
  them.
- This sandbox has no network access. That has been true since Phase 4
  and remains true now — it is not a new or milestone-specific
  limitation.
