# Payments (Phase 6 Milestone 1; `refund_payment` added in T-3)

Scope of Milestone 1: `create_payment_session` and `get_payment_status`
only. `refund_payment` was reserved (staff/admin-only, in
`TOOL_AUTHORIZATION_MATRIX`) but not implemented at that time — it is now
(§9, this session). Email/SMS delivery of the payment link is still
explicitly **not** built — see "Known limitations" below.

## 1. Architecture

```
Web browser                    Vapi voice call
     |                                |
     v                                v
app/api/routes/payments.py    app/api/routes/vapi.py
require_payment_access()      REQUIRES_VERIFIED_BOOKING
(owner or FINANCE/ADMIN,      (verification token — same
 never a token)                gate cancel/modify use)
     |                                |
     +---------------+----------------+
                      v
          app/services/payment_service.py
             PaymentService (ONE service,
             no channel-specific logic)
                      |
                      v
        app/providers/payments/base.py
             PaymentProvider (abstract)
              /                      \
    MockPaymentProvider        StripePaymentProvider
    (deterministic,             (real, uses the `stripe`
     dependency-free)            SDK — see §2)
```

Same shape as the airline provider layer (`AirlineProvider` /
`MockAirlineProvider` / `AmadeusAirlineProvider`) and the same rule as
Milestone 1's authorization spec: **Vapi is a conversation layer, never a
second implementation of payment logic.** `app/api/routes/vapi.py`'s
`_dispatch_create_payment_session`/`_dispatch_get_payment_status` call
the exact same `PaymentService` methods the web route calls — nothing
Stripe-specific exists in `vapi.py` at all.

## 2. Stripe integration

The primitive is a **Checkout Session** (Stripe's hosted, secure payment
page) — not a raw `PaymentIntent` embedded anywhere in the Vapi
conversation. This is what makes it possible to satisfy "the Vapi agent
must never collect or store raw card information": the tool hands back a
URL to Stripe's own page; nothing in this codebase ever sees a card
number.

`app/providers/payments/stripe_provider.py` is **written and
cross-checked against Stripe's current documentation (fetched while
building this milestone), but NOT executed** — `stripe>=11.1,<12.0` is
pinned in `requirements.txt` but this sandbox has no network access to
install it (same constraint as the entire FastAPI/SQLAlchemy layer since
Phase 4). Specifically verified against live documentation rather than
assumed from training data:
- Checkout Session field names (`id`, `url`, `status`, `payment_status`,
  `expires_at` as a unix timestamp, `amount_total`, `currency`,
  `payment_intent`).
- The exact four webhook event types this system reacts to, and the
  documented ambiguity that motivated keying transitions on event *type*
  rather than the `payment_status` field alone (see §3).
- Error class import paths: `stripe.error.SomeError` (the long-documented
  path) was confirmed broken in current `stripe-python` releases (an open
  upstream issue) — this codebase imports error classes from the
  top-level `stripe` module instead (`stripe.StripeError`,
  `stripe.SignatureVerificationError`, `stripe.InvalidRequestError`),
  which Stripe's own current docs use.
- Resource calls use the long-stable legacy style
  (`stripe.checkout.Session.create/retrieve`, module-level
  `stripe.api_key`) rather than the newer `StripeClient` object, because
  live sources disagreed on that object's exact method namespace for
  this pinned version range — see the module's docstring for the full
  reasoning. **"Verified against documentation" is not the same claim as
  "was run."** Do not mark this file execution-verified until it has
  actually processed a real Stripe test-mode Checkout Session.

`PAYMENT_PROVIDER` (`.env` — `mock` | `stripe`, default `mock`) selects
between providers via `app/providers/payments/__init__.py`'s factory,
mirroring `AIRLINE_PROVIDER` exactly. Selecting `mock` never requires
`stripe` to be importable at all — the factory only imports
`stripe_provider.py` inside the `stripe` branch.

## 3. Payment states

Five states, derived from Stripe's actual Checkout Session lifecycle (not
copied verbatim from an earlier six-state sketch that included a raw-
PaymentIntent-only concept Checkout Sessions never surface at this
level) — full reasoning and the allowed-transition table are in
`app/core/payments/state_machine.py`'s module docstring:

| Status | Meaning | Terminal? |
|---|---|---|
| PENDING | Session created, awaiting the customer | No |
| PROCESSING | `.completed` fired but an async payment method is still settling | No |
| SUCCEEDED | Payment captured | Yes |
| FAILED | An async payment method ultimately failed | Yes |
| EXPIRED | The 24h window elapsed, nothing was ever charged | Yes |
| CANCELED | Charter123-side administrative supersession (bookkeeping only — no tool causes this) | Yes |

This maps onto the **pre-existing** `Booking.payment_status` vocabulary
(`UNPAID`/`PENDING`/`PAID`/`REFUNDED`/`FAILED` — unchanged since Phase
1-3) via `BOOKING_PAYMENT_STATUS_FOR_SESSION` — no new value was added to
`Booking.payment_status`, per this milestone's instruction not to invent
booking states without examining the existing lifecycle.
`Booking.status` (the separate provider/PNR lifecycle field) is **never**
touched by payments — `BookingService.create_booking` already sets it to
`CONFIRMED` independent of payment status, confirming these two fields
are deliberately orthogonal axes in the existing schema.

The one non-obvious mapping rule: `checkout.session.async_payment_failed`
still carries `payment_status: "unpaid"` on its embedded session object
(Stripe's Checkout Session `payment_status` field only ever takes
`paid`/`unpaid`/`no_payment_required` — there's no distinct "failed"
value at that level), so `new_status_for_webhook_event()` keys primarily
on the **event type**, not the `payment_paid` boolean alone — see that
function's docstring and
`tests/test_payments_core.py::WebhookEventMappingTests`.

## 4. Idempotency (stated honestly, not oversold)

- Same `idempotency_key` retried while the first attempt is
  `in_progress` -> rejected (`PAYMENT_SESSION_IN_PROGRESS`), not
  duplicated.
- Same `idempotency_key` retried after completion -> replays the same
  `Payment` row.
- The key is **also** forwarded to Stripe itself
  (`StripePaymentProvider` passes it as Stripe's own `idempotency_key`)
  — this is what actually protects the "Stripe created the session but
  our commit crashed before saving it" race: a retry with the same key
  gets Stripe's cached session back, not a second charge-capable one. If
  that key is never retried, the orphaned session just expires after
  24h — an abandoned checkout page, not a duplicate charge. **That is the
  real guarantee; nothing here claims stronger than that**, per this
  milestone's explicit instruction not to claim perfect distributed
  exactly-once semantics.
- A **different** idempotency key for a booking that already has a
  PENDING/PROCESSING payment does not start a second concurrent
  session — `PaymentRepository.get_open_for_booking()` is a booking-level
  guard, independent of the key-level one.
- `Payment.idempotency_key` and `Payment.provider_session_id` both carry
  a database `UNIQUE` constraint — the actual backstop against a
  genuinely concurrent double-submission slipping past the in-memory
  `IdempotencyStore` (documented as not multi-instance-safe since it was
  introduced — see `app/core/idempotency.py`): the second `INSERT` fails
  at the database rather than silently succeeding twice.
- Stripe webhook **events** are deduplicated through the same
  `IdempotencyStore`, keyed `stripe_event:{event_id}` (namespaced so it
  can never collide with `derive_idempotency_key()`'s `idem_...` keys) —
  not a second, invented dedup mechanism.

## 5. Stripe webhook

`POST /api/v1/payments/webhooks/stripe` — no authentication dependency;
the `Stripe-Signature` header **is** the authentication, verified inside
`PaymentProvider.verify_and_parse_webhook()`. An invalid signature raises
`WebhookVerificationError`, caught by the `PaymentProviderError` handler
registered in `app/core/exceptions.py` and turned into HTTP 400 — never a
200. This is a genuine trust boundary (§9 of the milestone spec), unlike
the Vapi webhook's "always 200" contract, which is Vapi-specific.

Every other outcome (duplicate delivery, an event for a session this
system has no record of, an irrelevant event type, a payment that already
moved past this transition) is accepted with a 2xx and a descriptive
`outcome` string, never an error — Stripe redelivers on any non-2xx
response, and none of those cases should trigger a retry loop.

**Deliberately not rate-limited** in this milestone, unlike the Vapi
webhook's `vapi_webhook` profile — a request without a valid signature is
rejected regardless of volume, so throttling doesn't change the
security-relevant property the way it does for the Vapi endpoint. Scoped
out explicitly, not an oversight.

## 6. Authorization

Two gates, one service — see `docs/SECURITY.md` §22 for the full
reasoning and `app/api/deps_auth.py::require_payment_access` /
`app/core/security/vapi_authorization.py`'s `create_payment_session`/
`get_payment_status` entries for the code. In short:
`authorize_payment_access()` (Phase 4, unchanged, tested since before any
payment backend existed) has no verification-token path at all, so it's
reserved for the authenticated-web-owner-or-staff case; the voice path
uses the already-registered `REQUIRES_VERIFIED_BOOKING` gate instead —
the same one `cancel_booking`/`modify_booking` already use.

`refund_payment` (T-3) uses the SAME `authorize_payment_access()` gate as
the other two web routes, with `required_permission=PAYMENTS_REFUND` —
but has no voice path at all, by design: `PAYMENTS_REFUND` is only ever
held by FINANCE/ADMIN/SUPER_ADMIN (`app/core/security/rbac.py`), so a
customer-owner is denied by the same "missing_permission_for_self_access"
branch that already existed; a `VAPI_AGENT`/`ANONYMOUS_VERIFIED` actor is
denied because `authorize_payment_access` never accepts a
`verification_purpose` at all (see that function's own §14 note). This
was true before T-3, unchanged by it — T-3 only adds the route that
finally exercises the already-correct policy.

## 7. Vapi payment flow & confirmation rules

`create_payment_session` requires `customer_confirmed: true` in its tool
call, enforced the same way as `cancel_booking`/`modify_booking`/
`remove_passenger`: the mapper checks `args.get("customer_confirmed") is
not True` — an omitted field, `"true"` the string, or `1` the int all
raise `CONFIRMATION_REQUIRED`, only the literal boolean `True` passes
(see `tests/test_vapi_core.py::MutatingToolMappingTests.
test_create_payment_session_rejects_truthy_non_boolean_confirmation`).
The tool's own description instructs the assistant to read back the exact
total **before** setting that flag.

**Voice payment safety:** the assistant must never ask for a card number,
CVV, PIN, or one-time passcode — `create_payment_session`'s tool
description says so explicitly, and there is no parameter in its JSON
schema a card number could even be placed into. The caller completes
payment on Stripe's own hosted page, not through the phone call.

**Amount safety:** `PaymentSessionCreateRequest` has no `amount` or
`currency` field at all — `PaymentService.create_payment_session` always
reads `Booking.total_price`/`Booking.currency` itself. There is nothing
for an LLM-supplied (or forged) amount to flow through; see
`tests/test_vapi_core.py::MutatingToolMappingTests.
test_create_payment_session_ignores_llm_supplied_amount`.

## 8. Known limitation: out-of-band delivery

`create_payment_session` returns the Stripe Checkout URL as **data** —
the dispatch function's result string includes it, for the assistant to
work with. It does **not** claim the caller has received or can access
that link, and the tool's own description explicitly instructs the
assistant not to say it's been sent. **Actually delivering it (email or
SMS) is not part of this milestone** and was explicitly scoped out:

- `app/services/email_provider.py`'s only implementation is
  `MockEmailProvider` — not a production delivery mechanism.
- No SMS provider exists anywhere in this codebase (`TWILIO_*` config
  variables are pre-wired in `.env.example`/`config.py`, nothing is built
  on them).
- A phone caller who needs the link delivered has no path to receive it
  today except a human transfer (`transfer_to_human`) — the tool's
  description says as much.
- **Do not silently add Resend/Twilio/any delivery provider to close
  this gap** — it needs its own milestone with its own review, not a
  quiet addition here.

## 9. Refund payment (T-3 — was "Known limitation: cancellation does not call the payment provider")

**Fixed this session.** Before T-3, `CancellationService.cancel()` flipped
`Booking.payment_status` from `PAID` to `REFUNDED` locally without ever
calling `PaymentProvider`/Stripe — a cancelled, previously-paid booking
reported `REFUNDED` without a real refund having occurred. This was
tracked explicitly (not an oversight) and is now closed:

- **`PaymentProvider.refund_payment()`** (new abstract method) +
  `RefundResult`/`RefundStatus`/`PaymentRefundError`, implemented in both
  `MockPaymentProvider` (deterministic, dependency-free) and
  `StripePaymentProvider` (`stripe.Refund.create` against the
  PaymentIntent, cross-checked against Stripe's current Refunds API
  reference this session).
- **`CancellationService.cancel()`** now calls it directly for a `PAID`
  booking, using the airline's `CancellationResult.refundable_amount`
  (net of `cancellation_fee` — a cancellation fee is real money the
  airline keeps, refunding the full `Payment.amount` regardless would be
  wrong). Always sets `Booking.payment_status = "REFUNDED"` on a
  successful paid cancellation, full or fee-adjusted. If the refund call
  itself fails, the airline cancellation is **not** rolled back (it
  already happened and can't be undone locally) —
  `Booking.payment_status` stays `"PAID"` (never falsely `"REFUNDED"`),
  an audit event (`payment.refund_failed_during_cancellation`) records
  it, and staff can complete it manually via the new standalone route
  below.
- **`POST /api/v1/payments/refunds`** — a new, separate, staff-only
  (`PAYMENTS_REFUND`) REST route for a manual/goodwill refund on an
  *active* booking, independent of cancellation. A partial refund here
  only flips `Booking.payment_status` to `"REFUNDED"` once the
  cumulative refunded amount covers the full payment — otherwise the
  booking stays `"PAID"` (it's still a valid, active booking, just
  partially refunded).
- **Design note — `Payment.status` is never mutated by a refund.** It
  stays `"SUCCEEDED"` forever once paid; refund tracking lives entirely
  in five new columns on `Payment`
  (`provider_refund_id`/`refunded_amount`/`refund_status`/`refunded_at`/
  `refund_reason`, migration `0005`) — orthogonal to
  `app/core/payments/state_machine.py`'s session-status vocabulary,
  which T-3 deliberately did NOT touch. This keeps
  `tests.test_payments_core.StateMachineTests.
  test_booking_payment_status_mapping_never_produces_refunded` (and
  every other `StateMachineTests` assertion) true without modification —
  confirmed by re-running the full dependency-free suite after the
  change (see §12).
- **Known gap this still leaves:** no webhook subscription for Stripe's
  `refund.updated`/`charge.refunded` events. A refund that comes back
  `pending`/`requires_action` from the synchronous `POST /v1/refunds`
  call is recorded as such (`Payment.refund_status`), but nothing
  resolves it to `succeeded`/`failed` later on its own — `Booking.
  payment_status` stays unchanged until it's checked again. This was
  explicitly out of T-3's scope (see `docs/TASK_BOARD.md`) — a future
  milestone would add a `refund.*` case to
  `PaymentProvider.verify_and_parse_webhook`/`PaymentService.
  handle_webhook_event`, mirroring how `checkout.session.completed`
  already works.

## 10. Environment variables

```
PAYMENT_PROVIDER=mock        # mock | stripe
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
```

Both Stripe variables are only required when `PAYMENT_PROVIDER=stripe` —
`Settings.validate_for_production()` checks this conditionally, mirroring
`AIRLINE_PROVIDER`'s existing mock/real split.

## 11. Local development

1. Leave `PAYMENT_PROVIDER=mock` (the default) — no Stripe account
   needed. `MockPaymentProvider` is deterministic: the same
   `idempotency_key` always produces the same session id
   (SHA-256-derived, not random), and `simulate_completion()`/
   `simulate_expiry()`/`build_webhook_event()` let a test or a manual
   script drive the exact lifecycle it wants without any network call.
2. To test against real Stripe: set `PAYMENT_PROVIDER=stripe` and both
   Stripe variables to **test-mode** values, install `stripe` (`pip
   install -r requirements.txt`), and use the Stripe CLI
   (`stripe listen --forward-to localhost:8000/api/v1/payments/webhooks/stripe`)
   to receive webhook events locally. This has not been done from this
   sandbox (no network access) — see §12.

## 12. Production setup / runtime verification status

| Component | Status |
|---|---|
| `app/core/payments/state_machine.py` | **Executed** — 15 tests, `tests/test_payments_core.py::StateMachineTests`/`WebhookEventMappingTests` (unchanged by T-3 — deliberately not modified; corrected this session from the previous "12" in this table, which undercounted `WebhookEventMappingTests`) |
| `app/providers/payments/base.py`, `mock.py` | **Executed** — 31 tests, `tests/test_payments_core.py::MockPaymentProviderTests`/`PaymentProviderErrorTests`/`RefundResultTests`/`MockPaymentProviderRefundTests` (13 new for T-3's `refund_payment`) |
| `app/core/vapi/argument_mapping.py`'s two new mappers | **Executed** — 9 tests in `tests/test_vapi_core.py::MutatingToolMappingTests` |
| `authorize_payment_access` denial of `VAPI_AGENT`/`ANONYMOUS_VERIFIED` for `payments.create`/`payments.read`/`payments.refund` | **Executed** — `tests/test_security_core.py::OwnershipTests`, including the pre-existing `test_finance_role_can_refund_anyone` (T-3 didn't need to touch this file — the policy was already correct) |
| `refund_payment` never becoming a Vapi-callable tool | **Executed** — `tests/test_vapi_core.py::ToolRegistryConsistencyTests.test_authorization_entries_without_a_schema_are_exactly_staff_only` (pre-existing test, re-confirmed still passing after T-3) |
| `app/providers/payments/stripe_provider.py` (including `refund_payment`, T-3) | **Written, verified against current Stripe documentation, NOT executed** — no network access to install `stripe` |
| `app/models/payment.py`, migrations `0004`/`0005`, `app/repositories/payment_repository.py`, `app/services/payment_service.py` (including T-3's `apply_refund_outcome`/`refund_payment`), `app/services/cancellation_service.py` (T-3's refund wiring), `app/api/routes/payments.py` (including T-3's `POST /refunds`), `vapi.py`'s dispatch functions | **Written, reviewed against verified method signatures, NOT executed** — needs FastAPI/SQLAlchemy/a real Postgres, none installable here (same constraint as the entire FastAPI layer since Phase 4; re-confirmed this session: `python3 -c "import fastapi"` / `sqlalchemy` / `stripe` all raise `ModuleNotFoundError`) |
| A real Stripe Checkout Session, or a real Stripe refund, actually completing end-to-end | **Not attempted** — requires a live Stripe test-mode account |

Before a production launch that actually charges (or refunds) customers:
run `alembic upgrade head` against a real Postgres and confirm migrations
`0004`/`0005` apply cleanly in sequence; install the full stack and run
`tests/test_api_security.py`/`test_vapi_api.py` for real (this remains
the single highest-value next step for the whole Vapi+payments surface,
not new to this milestone); complete a real Stripe test-mode Checkout
Session AND a real test-mode refund end-to-end, including real webhook
delivery via `stripe listen` or a configured endpoint; then run
PCI-relevant configuration review (this integration never touches raw
card data by design — see §2 — but Stripe Checkout's own domain/
branding/webhook-endpoint setup still needs a human to configure and
verify in the Stripe Dashboard).

## 13. Known limitations (summary)

- Out-of-band delivery of the payment link (§8) — not built, scoped out.
- Cancellation's refund now calls the real payment provider (§9, fixed
  in T-3) — but there's still no webhook subscription for Stripe's
  `refund.updated`/`charge.refunded` events, so a non-instant
  (`pending`/`requires_action`) refund is recorded as such and never
  auto-resolves — scoped out of T-3, see §9's last bullet.
- Stripe webhook has no rate limiting (§5) — scoped out, reasoning given.
- `StripePaymentProvider` (including `refund_payment`) is unexecuted
  (§2/§9/§12).
- The entire FastAPI/SQLAlchemy layer this milestone (and T-3) added is
  unexecuted in this sandbox (§12) — same constraint as every prior
  phase.
