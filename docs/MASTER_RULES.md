# Charter123 — Master Rules

Non-negotiable engineering invariants. These do not expire when a phase
ends, and they are not superseded by status changes elsewhere — violating
one is a defect at any point in the project's life, regardless of what
`docs/TASK_BOARD.md` currently authorizes.

Consolidated from the Master Build Prompt (§20, §60, §77 primarily) and
the "do-not-change architectural invariants" sections of
`PROJECT_HANDOFF_PHASE_4.md` §20, `PROJECT_HANDOFF_PHASE_5.md` §18, and
`docs/PAYMENTS.md`/`docs/handoffs/2026-09-06-phase6-milestone1-payments.md`.
Where a source document's own invariant list is more detailed than what's
below, that document's list still stands — this file is the cross-phase
summary, not a replacement.

## 1. The backend is always the source of truth

- The LLM (Vapi) is never authoritative for a fact, a price, availability,
  a booking status, or whether an action succeeded. It only ever repeats
  what a tool call returned.
- Never claim (in speech, in a response body, or in a log) that an action
  succeeded before the backend has actually confirmed it — a definite
  result or a structured error, never a "probably worked" state.
- Never invent flight numbers, prices, aircraft, availability, PNRs,
  refund amounts, cancellation fees, passenger records, booking status,
  payment status, departure/arrival times, airport information, or
  policy. If the backend doesn't have it, say so honestly — don't fill
  the gap.

## 2. Never trust client-supplied identity

- Never treat `x-user-id`, `x-admin-id`, `customerId`, `bookingId`, or any
  similarly-named client-supplied header/field as identity or
  authorization. `CurrentActor` is derived only from a verified session
  cookie, a verified Vapi webhook shared secret, or a redeemed
  verification token — never from a request header whose value the
  caller chose.
- **Known current exception, not yet fixed** (`docs/PROJECT_ROADMAP.md`
  §6.6): the direct REST booking routes read `x-charter123-call-id`
  unauthenticated for an audit-log display string only. This does not
  grant access to anything, but it is exactly the pattern this rule
  exists to prevent and should be fixed rather than extended.
- Authorization decisions belong in `app/core/security/*.py`
  (`ownership.py`, `vapi_authorization.py`, `rbac.py`) — never in a
  route handler, never in a Vapi system prompt. If you're about to add
  an `if` that decides allow/deny somewhere else, it belongs in one of
  those files instead.

## 3. Explicit confirmation before any mutation with consequences

- `create_booking`, `cancel_booking`, `modify_booking`, `remove_passenger`,
  `create_payment_session` all require an explicit, literal `True` for
  `customer_confirmed` (or, for `create_booking`, a specific `quote_id`
  reference as the implicit commitment) — never inferred from the caller
  continuing the conversation, and never satisfied by a truthy
  non-boolean (`"true"`, `1`).
- A quote expires (15 minutes in `MockAirlineProvider`) and a booking may
  not be created against an expired one (`FARE_EXPIRED`).
- Cancellation and payment-session creation must be idempotent — retrying
  the same logical request must not double-cancel or double-charge.

## 4. Provider abstraction — never hard-code a concrete integration

- Application code calls `AirlineProvider`/`PaymentProvider` interfaces,
  never `MockAirlineProvider`/`StripePaymentProvider`/etc. directly,
  except inside the one factory function each (`get_airline_provider()`,
  the payments provider factory) that reads the relevant `*_PROVIDER`
  environment variable.
- Never fabricate an undocumented third-party API. If credentials/docs
  for a real provider aren't available, implement the interface as a
  loud `NotImplementedError` placeholder (see `amadeus.py`/`sabre.py`),
  never a guessed implementation.
- A provider's error types translate into this codebase's own
  `ProviderError`/`PaymentProviderError` subclasses at the provider
  boundary — a raw third-party exception (a Stripe error, an HTTP error
  from a real GDS) must never reach a route handler or a customer-facing
  message.

## 5. Sensitive data handling

- Never store raw payment card data — Stripe Checkout Sessions only; no
  parameter in any tool schema can carry a card number, CVV, PIN, or OTP.
- Never put an amount/currency field in a request an LLM or caller
  populates — `PaymentService` always reads `Booking.total_price`/
  `Booking.currency` itself.
- Passport numbers are encrypted at rest (`app/core/encryption.py`) and
  never returned in full — masked, last-4-only forms.
- Never log passwords, API keys, passport numbers, payment card data, or
  session/verification/CSRF tokens — everything passes through
  `app/core/security/redaction.py` first.
- Never read a full passport number aloud or put one in a Vapi tool
  parameter.

## 6. Vapi-specific invariants (from Phase 5/6 handoffs, still binding)

- `authorize_vapi_tool_call()`'s sensitivity check runs **before** its
  permission check — this is what makes `VAPI_ASSISTANT_PERMISSIONS`
  being broad on paper harmless. Do not reorder this.
- Never give the Vapi assistant a tool for `send_confirmation`/
  `send_sms`/`send_email` — these are system-triggered side effects,
  never an LLM-invoked action.
- `verify_booking_customer`'s tool schema never exposes a `purpose`
  parameter — the Vapi channel always verifies for the single fixed
  `"vapi_tool_access"` purpose.
- Never derive a mutating tool's `idempotency_key` from anything the LLM
  supplies — always `derive_idempotency_key(call_id, operation, payload)`,
  server-side.
- A custom webhook tool (like `transfer_to_human`) must never claim a
  live call transfer happened — only Vapi's native `transferCall` tool
  can move a call. A custom tool's result text must never imply
  otherwise.
- Do not re-duplicate `redeem_verification_token()` — it is the one place
  every channel (web, Vapi) redeems a verification token. Extend it if a
  third channel needs this; don't copy it.
- Do not mark an "intentionally unavailable" tool as implemented without
  first checking whether the underlying domain model actually exists now
  — re-verify by grepping for the model, don't assume from a prior
  phase's note (this is exactly the kind of claim that goes stale — see
  `docs/PROJECT_ROADMAP.md` §6.2/§6.3 for two real examples).
- `docs/VAPI.md`'s tool table and `tests/test_vapi_core.py::
  ToolRegistryConsistencyTests` must never be allowed to drift from each
  other — hand-editing the schema registry or the authorization matrix
  without updating both together will get caught by that test; don't
  work around the test instead of fixing the drift.

## 7. Testing and honesty about verification status

- Never represent code as "tested" or "verified" unless it was actually
  executed in this session (or a prior one, with the command and result
  shown). Distinguish, explicitly, in every handoff and status update:
  **Verified locally** (executed, with a test count) vs. **Written,
  reviewed, not executed** vs. **Requires external verification** (needs
  a live third-party account/call this environment cannot provide).
- Do not claim tests passed if the required dependencies are unavailable
  — a clean skip is not a pass, and both are different from a failure.
- Re-run the full dependency-free suite after any change, not just the
  file you touched — `docs/PROJECT_ROADMAP.md`'s exact command is:
  `cd apps/api && python3 -m unittest tests.test_core_logic
  tests.test_security_core tests.test_vapi_core tests.test_payments_core
  tests.test_api_security tests.test_vapi_api tests.test_notifications_core
  tests.test_admin_core -v`
  (`tests.test_admin_core` added 2026-09-11, T-6 — 289 tests total, 8
  skips, as of that session).

## 8. Documentation discipline

- Preserve the Master Build Prompt's original phase numbering exactly —
  never silently renumber a phase to match implementation order (see
  `docs/PROJECT_ROADMAP.md` §6.1 for the one case this project already
  got wrong once).
- When you find documentation that disagrees with the repository, record
  the discrepancy (in `docs/PROJECT_ROADMAP.md`) rather than silently
  fixing the doc to match your assumption of what's "obviously" true —
  and rather than silently trusting the doc. Verify against the actual
  file (see §6.3 of the roadmap: a documented "known gap" that had been
  carried forward, uncorrected, across two phase handoffs turned out not
  to exist on inspection).
- Frozen historical handoffs (`PROJECT_HANDOFF_PHASE_*.md`,
  `docs/handoffs/*.md`) are never rewritten to pretend they described a
  later state. If they conflict with the repository, the conflict gets
  recorded in `docs/PROJECT_ROADMAP.md`, not silently edited away.
- `docs/PRODUCTION_CHECKLIST.md` tracks verification status
  (Definition-of-Done, line by line). It is not the roadmap and must
  never be treated as the place sequencing decisions live — that's
  `docs/PROJECT_ROADMAP.md` and `docs/WORK_BREAKDOWN_STRUCTURE.md`.

## 9. Don't-do list (Master Build Prompt §77, still binding)

Do not: create fake API endpoints for real providers · hard-code secrets
· put secrets in frontend code · trust LLM-generated customer IDs or
authorization · expose raw database errors or stack traces to clients ·
book/cancel/charge without explicit confirmation · invent prices, flights,
or aircraft availability · claim success before backend confirmation ·
store raw payment card data · log passport numbers · create one giant
backend file · build a frontend-only fake booking system · rely on
`localStorage` as a database (note: this also applies to any future React
artifact/UI work — Charter123's own frontend must never do this either)
· use mock data in production · use deprecated Vapi custom functions when
the Tools API is available.
