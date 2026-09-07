# Booking Flow

## The rule that shapes everything here

> The LLM is never the source of truth. The backend is authoritative.

Concretely, this codebase enforces it in three places:

1. **`BookingCreateRequest`/`BookingCancelRequest`/`BookingModifyRequest`
   require a `customer_confirmed` / valid `quote_id` before anything
   transactional happens.** `CancellationService.cancel()` and
   `BookingService.modify_booking()` both raise
   `CONFIRMATION_REQUIRED` if `customer_confirmed` isn't `True` — see
   `app/services/cancellation_service.py` and `booking_service.py`.
   **Updated 2026-09-07 — Phase 5 (Vapi) is built now; this note was
   stale.** `customer_confirmed` is still, structurally, a boolean the
   caller sets — for the Vapi channel, that means the LLM, guided by each
   tool schema's description (`app/core/vapi/tool_schemas.py`: e.g.
   *"only set that after the caller has..."*) telling it to set it only
   after actually hearing a yes. That part is an inherent limit of any
   voice-confirmation design, Charter123's included — some layer always
   has to trust that the agent relayed the customer's answer honestly;
   see `docs/MASTER_RULES.md` §3. What Phase 4/5 did add, so this is no
   longer "nothing stops a caller": the Vapi webhook itself requires a
   valid shared secret before any tool call is even considered
   (`app/core/security/vapi_webhook_auth.py`), and `cancel_booking`/
   `modify_booking`/`remove_passenger`/`create_payment_session` all *also*
   now require a separately-issued `verification_token`
   (`BookingVerificationService`) alongside `customer_confirmed` — so a
   sensitive mutation needs both "confirmed" and "verified," not just
   one boolean. Routes are no longer bare/internal-only either — Phase 4
   added real session auth + RBAC on the web side. See
   `docs/ARCHITECTURE.md`'s "Trust boundary" section for the current,
   accurate picture, including one real residual gap this project's
   2026-09-07 audit found (`docs/PROJECT_ROADMAP.md` §6.6).
2. **A fare quote is required to book, and it expires.**
   `MockAirlineProvider` holds quotes for 15 minutes
   (`_QUOTE_VALIDITY_MINUTES`); `create_booking()` raises `FARE_EXPIRED`
   past that window rather than booking at a stale price. This is
   verified by `test_expired_quote_cannot_be_booked` in
   `tests/test_core_logic.py`.
3. **Nothing is spoken/shown as successful until the backend confirms
   it.** The API's job is to make this trivial for whatever calls it: a
   booking/cancellation either returns a definite result or raises a
   structured `ProviderError`/`AppError` — there's no "probably worked"
   state.

## Identity verification (§13)

Knowing a PNR is not authorization. `BookingVerificationService`
(`app/services/verification_service.py`) requires the caller to also
supply the contact email/phone on file, or a passenger's last name, before
`GET`-style lookup returns anything. It's intentionally simple (exact,
case-insensitive match) — production should add rate-limiting per PNR via
Redis to slow down guessing, which isn't implemented yet.

## Idempotency (§27)

Two layers exist, and it's worth knowing which is which:

- **`app/core/idempotency.py`** — the *application-level* store
  (`IdempotencyStore` protocol). `BookingService`/`CancellationService`
  call `.begin(key)` before doing anything, and `.complete(key, result)`
  after. The default implementation, `InMemoryIdempotencyStore`, is
  **single-process only** — fine for this sandbox and for local dev, not
  sufficient for a multi-instance production deployment. A
  `idempotency_keys` Postgres table (`app/models/idempotency.py`) and a
  `IdempotencyKeyRecord` model already exist for a durable version; wiring
  a Redis- or Postgres-backed `IdempotencyStore` implementation is
  flagged as a TODO in `app/api/deps.py::get_idempotency_store()`.
- **`MockAirlineProvider`'s own internal dedup** (`_idempotency_seen`
  dict) — simulates how a *real* GDS would also want an idempotency key on
  order-creation calls. This is separate from the application-level store
  above and would exist independently of it with a real provider.

The key itself is derived deterministically from
`(call_id, operation, canonical_request_payload)` — see
`derive_idempotency_key()` — so retrying the exact same logical request
always maps to the same key.

## What "modify" currently supports

`BookingModifyRequest` supports rebooking to a different flight
(`new_flight_id`) and updating contact info. Seat selection, baggage
add-ons, and special-assistance updates (§16) go through the passenger
endpoints (`add_passenger`/`add_passport_details` in
`app/services/passenger_service.py`) rather than `modify_booking` — there
isn't a dedicated "add baggage" or "select seat" endpoint yet; that's
flagged in PRODUCTION_CHECKLIST.md.

## Passport data (§10)

Passport details are **not** part of the initial booking request — they're
a separate call (`POST /api/v1/passengers/{pnr}/{passenger_id}/passport`)
so the flow never asks for a passport number until it's actually needed.
The number is encrypted before it touches the database
(`app/core/encryption.py`) and is never returned in full — only a masked
`***XXXX` form (`mask_for_speech`), and only the last-4 form ever gets
decrypted, purely to build that mask.
