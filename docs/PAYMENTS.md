# Payments (Phase 6 Milestone 1)

Scope of this milestone: `create_payment_session` and `get_payment_status`
only. `refund_payment` (staff/admin-only, already reserved in
`TOOL_AUTHORIZATION_MATRIX` since an earlier phase) and any email/SMS
delivery of the payment link are explicitly **not** part of this
milestone — see "Known limitations" below.

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

## 9. Known limitation: cancellation does not call the payment provider

`CancellationService.cancel()` (pre-existing, unmodified logic) flips
`Booking.payment_status` from `PAID` to `REFUNDED` locally — it does
**not** call `PaymentProvider` or Stripe to actually refund anything.
Before this milestone, `payment_status` could never actually reach
`PAID` in practice, so this line was effectively dead code. **It is
reachable now.** A cancelled, previously-paid booking will report
`REFUNDED` without a real refund having occurred. This is explicitly out
of this milestone's scope (`create_payment_session` + `get_payment_status`
only) — `refund_payment` is a separate, already-reserved
`STAFF_OR_ADMIN_ONLY` tool for a future milestone to actually implement
against `PaymentProvider`. Flagged here, and with an inline comment at
the exact line in `cancellation_service.py`, specifically so it isn't
mistaken for an oversight.

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
| `app/core/payments/state_machine.py` | **Executed** — 12 tests, `tests/test_payments_core.py::StateMachineTests`/`WebhookEventMappingTests` |
| `app/providers/payments/base.py`, `mock.py` | **Executed** — 17 tests, `tests/test_payments_core.py::MockPaymentProviderTests`/`PaymentProviderErrorTests` |
| `app/core/vapi/argument_mapping.py`'s two new mappers | **Executed** — 9 tests in `tests/test_vapi_core.py::MutatingToolMappingTests` |
| `authorize_payment_access` denial of `VAPI_AGENT`/`ANONYMOUS_VERIFIED` for `payments.create`/`payments.read` | **Executed** — `tests/test_security_core.py::OwnershipTests` |
| `app/providers/payments/stripe_provider.py` | **Written, verified against current Stripe documentation, NOT executed** — no network access to install `stripe` |
| `app/models/payment.py`, migration `0004`, `app/repositories/payment_repository.py`, `app/services/payment_service.py`, `app/api/routes/payments.py`, `vapi.py`'s two new dispatch functions | **Written, reviewed against verified method signatures, NOT executed** — needs FastAPI/SQLAlchemy/a real Postgres, none installable here (same constraint as the entire FastAPI layer since Phase 4) |
| A real Stripe Checkout Session actually completing end-to-end | **Not attempted** — requires a live Stripe test-mode account |

Before a production launch that actually charges customers: run
`alembic upgrade head` against a real Postgres and confirm migration
`0004` applies cleanly on top of `0003`; install the full stack and run
`tests/test_api_security.py`/`test_vapi_api.py` for real (this remains
the single highest-value next step for the whole Vapi+payments surface,
not new to this milestone); complete a real Stripe test-mode Checkout
Session end-to-end, including a real webhook delivery via `stripe
listen` or a configured endpoint; then run PCI-relevant configuration
review (this integration never touches raw card data by design — see §2
— but Stripe Checkout's own domain/branding/webhook-endpoint setup still
needs a human to configure and verify in the Stripe Dashboard).

## 13. Known limitations (summary)

- Out-of-band delivery of the payment link (§8) — not built, scoped out.
- Cancellation's refund flip is local-only (§9) — pre-existing, now
  load-bearing, not fixed in this milestone.
- Stripe webhook has no rate limiting (§5) — scoped out, reasoning given.
- `StripePaymentProvider` is unexecuted (§2/§12).
- The entire FastAPI/SQLAlchemy layer this milestone added is unexecuted
  in this sandbox (§12) — same constraint as every prior phase.
- `refund_payment` remains unimplemented — reserved, staff/admin-only,
  explicitly out of this milestone's scope.
