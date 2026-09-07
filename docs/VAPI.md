# Vapi Voice Agent Integration (Phase 5)

Referenced from `app/schemas/booking.py`. Technical reference for the
Vapi side of Charter123's voice channel.

**Status: written and internally consistent, verified where this
sandbox allows (dependency-free unit tests — 56 of them specific to
this phase, in `tests/test_vapi_core.py`), NOT verified against a real
Vapi account, a live phone call, or a real Postgres/Redis instance.**
Every claim below is labeled **Verified locally** or **Requires external
Vapi verification** — take the second label literally; nothing under it
has been exercised end-to-end.

## Architecture

```
Customer
  |
  v
Phone call --> Vapi (STT / LLM / TTS)
  |
  v
Vapi Assistant, configured with the tool list below
  |
  v  (tool call)
POST {server_url}/api/v1/vapi/webhook  <-- app/api/routes/vapi.py
  |
  v
1. Shared-secret check (app.core.security.vapi_webhook_auth)
2. Webhook-level rate limit, keyed by source IP (app.core.vapi.rate_limiting)
3. Parse arguments (app.core.vapi.argument_mapping)
4. Load booking BY PNR from Postgres, if the tool needs one
5. Redeem verification_token server-side (app.api.deps_auth.redeem_verification_token
   — shared with the web /bookings/{pnr}/verify path, not a separate copy)
6. Per-tool-call rate limit, keyed by Vapi call_id
7. authorize_vapi_tool_call() (app.core.security.vapi_authorization)
8. Same application service a web request would use
   (BookingService / CancellationService / PassengerService / FlightService)
9. Record a ToolExecution row; mutations also get an AuditLog row
   automatically (the service layer does this, not this route)
  |
  v
{"results": [{"toolCallId": "...", "result": "..."}]}  <-- always HTTP 200
```

Vapi is the conversation layer. It never touches Postgres, never makes an
authorization decision, and never originates a fact about a booking,
price, or PNR that didn't come back from a tool call — see **Voice Safety
Rules** below.

## Vapi Assistant configuration

**Server URL:** `https://<your-domain>/api/v1/vapi/webhook`

**Server URL secret:** set to the same value as `VAPI_WEBHOOK_SECRET`
(see `.env.example`). Vapi sends this back as either an `X-Vapi-Secret`
header or an `Authorization: Bearer <secret>` header depending on how the
credential is configured on Vapi's side — both are accepted
(`app/core/security/vapi_webhook_auth.py`). *Verified locally against
docs.vapi.ai's documented shared-secret model; requires external Vapi
verification that a real Vapi account sends one of these two header
forms and no other.*

**Tools (`model.tools`):** generate this list from code — it's the
source of truth:

```python
from app.core.vapi.tool_schemas import as_vapi_function_definitions
import json
print(json.dumps(as_vapi_function_definitions(), indent=2))
```

**Transfer tool:** ALSO create a native Vapi `transferCall` tool (Vapi
Dashboard -> Tools -> Create Tool -> Transfer Call), with a destination
number for Charter123's support line, and attach it to the assistant
alongside the tools above. See **Transfer to human** below for why this
is a second, separate tool rather than something `transfer_to_human`
itself does.

**Model / voice / transcriber:** not prescribed here — provider-agnostic
by design, since the tool-calling contract is what this integration
depends on, not a specific LLM/STT/TTS combination.

## The full tool list

Generated from `app/core/vapi/tool_schemas.py` — this table is a
human-readable summary; the code is authoritative.

**Status key:**
- **IMPLEMENTED** — wired to a real, existing application service; behaves as described once deployed.
- **PARTIALLY IMPLEMENTED** — the backend contract exists and does something real, but the full described behavior needs an external system this sandbox can't configure or verify.
- **INTENTIONALLY UNAVAILABLE** — registered (so the LLM can be told it exists and say "not available yet" instead of guessing) but the underlying Charter123 domain genuinely has no model for this yet — not an oversight, a scope question for a future milestone.

"Confirmation" means the system prompt must get an explicit yes before
the assistant sets `customer_confirmed: true` — the backend only
enforces that the flag is present and is literally `True` (not `"true"`,
not `1` — see `tests/test_vapi_core.py::MutatingToolMappingTests.
test_cancel_booking_rejects_truthy_non_boolean_confirmation`), not that a
human actually said yes; that part is prompt engineering, not security.

| Tool | Sensitivity | Mutates | Confirmation | Status |
|---|---|---|---|---|
| search_flights | Public | No | — | IMPLEMENTED |
| get_flight_details | Public | No | — | IMPLEMENTED |
| get_aircraft_availability | Public | No | — | IMPLEMENTED |
| get_fare_quote | Public | No | — | IMPLEMENTED |
| get_cancellation_policy | Public | No | — | IMPLEMENTED |
| get_baggage_policy | Public | No | — | IMPLEMENTED |
| verify_booking_customer | Public (produces verification) | No | — | IMPLEMENTED |
| get_booking | Requires verified booking | No | — | IMPLEMENTED |
| create_booking | Public (no prior owner) | Yes | Yes (implicit — see below) | IMPLEMENTED |
| modify_booking | Requires verified booking | Yes | Yes | IMPLEMENTED |
| cancel_booking | Requires verified booking | Yes | Yes | IMPLEMENTED |
| add_passenger | Requires verified booking | Yes | No | IMPLEMENTED |
| remove_passenger | Requires verified booking | Yes | Yes | IMPLEMENTED |
| transfer_to_human | Public | No (logs only) | — | PARTIALLY IMPLEMENTED — see below |
| add_baggage | Requires verified booking | Yes | Yes | INTENTIONALLY UNAVAILABLE — no baggage-mutation model exists |
| get_seat_options | Requires verified booking | No | — | INTENTIONALLY UNAVAILABLE — no seat map/inventory model exists (`BookingPassenger.seat_preference` is a free-text preference, not an assignable seat) |
| select_seat | Requires verified booking | Yes | No | INTENTIONALLY UNAVAILABLE — same reason |
| create_payment_session | Requires verified booking | Yes | Yes | IMPLEMENTED (Phase 6 Milestone 1) — see docs/PAYMENTS.md |
| get_payment_status | Requires verified booking | No | — | IMPLEMENTED (Phase 6 Milestone 1) — see docs/PAYMENTS.md |
| create_support_ticket | Requires verified booking | Yes | No | INTENTIONALLY UNAVAILABLE — no SupportTicket model |
| create_callback_request | Public | Yes | No | INTENTIONALLY UNAVAILABLE — no CallbackRequest model |

Re-verified during Phase 5.2 (not just carried over from 5.1): grepped
every model file for `seat`/`baggage`/`payment`/`support_ticket` — the
only matches were `BookingPassenger.seat_preference` (a preference
string) and `Aircraft`'s seat *count* (capacity, not a map); no
`Payment`/`SupportTicket`/`CallbackRequest` model existed anywhere in the
codebase at that time. **Phase 6 Milestone 1 changed this for payments
only**: `app/models/payment.py::Payment` now exists — see docs/PAYMENTS.md
for the full domain model, state machine, and authorization design.
`SupportTicket`/`CallbackRequest`/a seat map are still genuine domain
gaps, unaffected by this milestone.

`create_booking`'s confirmation is "implicit" rather than an explicit
flag: unlike cancel/modify, there's no pre-existing state to change
consent to — referencing a specific `quote_id` obtained from
`get_fare_quote` already IS the commitment being confirmed. The system
prompt should still read back the full itinerary and price before
calling it; nothing enforces that server-side, same as every other
confirmation on this list (the flag/reference is enforced; a human
actually having agreed is not and cannot be, from the backend's side).

`refund_payment` and `configure_assistant` exist in
`TOOL_AUTHORIZATION_MATRIX` (staff/admin-only) and are deliberately NOT
in this table or the Assistant's tool list — a voice agent can never
satisfy `STAFF_OR_ADMIN_ONLY`. `send_confirmation`/`send_sms`/
`send_email` are also deliberately absent — see
`vapi_authorization.py`'s comment on `TOOL_AUTHORIZATION_MATRIX`.

## Transfer to human — PARTIALLY IMPLEMENTED, external verification required

`transfer_to_human` (the custom tool hitting this webhook) does **not**
move the call — nothing a custom function tool returns can. Only Vapi's
own native `transferCall` tool can (confirmed against
`docs.vapi.ai/tools/transfer-call` and
`docs.vapi.ai/calls/call-dynamic-transfers`). `transfer_to_human`'s
actual job is to log the escalation (it gets a `ToolExecution` row like
every tool call, and its dispatch text is an instruction back to the
assistant — "Escalation logged. Use the transfer tool now..." — never a
claim to the caller that a transfer is happening, which would be exactly
the misleading-confirmation failure mode this needs to avoid).

**Required Vapi-side configuration** (not done, can't be done from this
sandbox): create a native `transferCall` tool with a phone-number
destination for Charter123's support line, attach it to the assistant,
and add a system-prompt line: *"When you need to escalate, call
transfer_to_human to log why, then immediately call the transfer tool to
connect them."* Vapi sets `endedReason` to `assistant-forwarded-call`
when a transfer via `transferCall` succeeds — this webhook already
captures `endedReason` into `Call.ended_reason` on the `end-of-call-
report` message, so once the native tool is configured, "did an
escalation actually complete" becomes observable without further backend
work. **Mark the end-to-end behavior IMPLEMENTED — EXTERNAL VAPI
VERIFICATION REQUIRED**, not fully verified, until a real call has been
transferred and that field checked.

## Payments (Phase 6 Milestone 1)

`create_payment_session`/`get_payment_status` are now implemented — the
full domain model, state machine, provider abstraction (mock + Stripe),
authorization reasoning, idempotency guarantees, and known limitations
all live in **docs/PAYMENTS.md** rather than being duplicated here. The
short version for this document's purposes: both tools use the SAME
`REQUIRES_VERIFIED_BOOKING` authorization path every other booking-scoped
tool on this list already uses — nothing in `vapi_authorization.py`
changed for this milestone; only `tool_schemas.py` (`implemented: True`,
plus a new `customer_confirmed` parameter on `create_payment_session`)
and `argument_mapping.py`/`vapi.py`'s dispatch table grew two new
entries.

## Rate limiting

**What's limited, keying, and limits** (`app/core/vapi/rate_limiting.py`
for the keying policy; `app/core/security/rate_limiter.py`'s existing,
Phase-4-tested `FixedWindowRateLimiter`/`RATE_LIMIT_PROFILES` for the
algorithm):

| Layer | Profile | Limit | Key | Rejection |
|---|---|---|---|---|
| Whole webhook endpoint | `vapi_webhook` | 120/min | source IP (`request.client.host`, or `"unknown"` if unavailable) | HTTP 429, before any parsing |
| Individual tool call | `vapi_tool` | 60/min | Vapi `call_id` | `results[].error` entry (stays inside the 200 contract Vapi expects) |
| Verification attempts | n/a — `BackoffLockout` | 5 failures before lockout; 2s -> 4s -> ... capped at 15min | `verify:{booking_id}` (derived inside `VerificationSessionService`, not by this route) | `AuthError(RATE_LIMITED)`, spoken as "Too many verification attempts..." |

**Why two different rejection styles**: the webhook-level and
verification-lockout rejections are transport/auth-adjacent facts about
the request as a whole ("this exceeds a volume threshold," "this
specific verification attempt is locked out") — treated the same as the
shared-secret check, a non-200 or a raised error, not a per-tool result.
The per-tool-call limit is checked *inside* the batch-processing loop for
one `toolCallId` among potentially several in one webhook POST (Vapi can
batch multiple tool calls into one request), so it has to produce a
`results[]` entry like every other tool outcome, or Vapi would be short
one result for a `toolCallId` it's expecting an answer for.

**Backoff behavior**: `BackoffLockout` is exponential (`base_backoff_seconds
* 2^(failures - threshold)`, capped at `max_backoff_seconds`), and a
single successful verification clears the counter entirely — see
`app/core/security/rate_limiter.py`'s own docstring, unchanged from
Phase 4. Not Vapi-specific; this is the exact same mechanism
`routes/auth.py`'s login endpoint already uses, just given a real
instance for the Vapi path where none was passed before.

**Tuning caveat**: `RATE_LIMIT_PROFILES["vapi_webhook"] = (120, 60.0)`
was chosen in Phase 4 as "a deliberately conservative starting point,"
before any real Vapi traffic pattern was known. Because Vapi's webhook
requests originate from Vapi's own infrastructure (not per-customer
IPs), if a single Charter123 Vapi account legitimately handles many
simultaneous real calls from the same source IP, this limit could
become a false-positive bottleneck rather than an abuse guard — this
needs revisiting against real traffic before a production launch at any
meaningful call volume, not treated as correctly calibrated because a
number exists.

**Verified locally**: the keying functions and the underlying
`FixedWindowRateLimiter`/`BackoffLockout` algorithms
(`tests/test_vapi_core.py::RateLimitKeyingTests`,
`VapiRateLimitProfileWiringTests`). **Requires external verification**:
that `request.client.host` reflects a useful source IP in the actual
deployment (a reverse proxy/load balancer in front of the API may need
`X-Forwarded-For` handling this route doesn't currently do — not
implemented, since there's no deployment topology to test it against
yet), and that Redis-backed rate limiting behaves correctly across
multiple API instances in production (only the in-process fallback has
ever run, in tests).

## Authorization: one shared model, not two

Phase 5.1 originally wrote the token-redemption logic
(`raw verification_token -> effective CurrentActor`) as a local copy
inside `app/api/routes/vapi.py`, since `app/api/deps_auth.py`'s
`require_booking_access()`/`require_passenger_access()` only performed
that redemption for `ActorType.ANONYMOUS_VERIFIED`, and editing an
untestable file felt like the wrong risk to take casually.

Phase 5.2 reconsidered this: that redemption logic was *already*
duplicated once, between `require_booking_access` and
`require_passenger_access`, before Vapi ever added a third copy. It's
now `app/api/deps_auth.py::redeem_verification_token()`, a single shared
function all three call sites use — see that function's docstring for
why extending its actor-type check to include `VAPI_AGENT` is safe for
every scenario Phase 4's tests already cover (the condition was false
for `VAPI_AGENT` before because nothing constructed one; it's a wholly
new, previously-unreachable branch, not a change to tested behavior).
**Not run against a real FastAPI test client** — this file still can't
be imported in this sandbox — but it is now exactly one function
maintaining the property "VAPI_AGENT/ANONYMOUS_VERIFIED redeem a token
the same way," instead of one function and a parallel hand-copy that
could drift from it.

`authorize_vapi_tool_call()` itself was NOT touched or reconciled with
`authorize_booking_access()`/`authorize_passenger_access()` — it's a
genuinely different, wider check (it also handles PUBLIC and
STAFF_OR_ADMIN_ONLY tools those two don't know about), and unifying them
would be exactly the "large refactor merely for elegance" this phase was
told not to do.

## Idempotency: the ToolExecution crash-recovery edge case

Phase 5.1 documented, rather than fixed, a case where a server crash
between claiming a `ToolExecution` row and finishing the request would
cause a retry to hit `vapi_tool_call_id`'s unique constraint. Phase 5.2
closes the *sequential* version of this (crash, then a later, separate
retry): the row is now claimed immediately (before parsing/authorization
run), and a retry that finds an existing row with `outcome IS NULL`
reuses and updates it in place instead of attempting a second insert.

This does **not** close a genuinely *concurrent* double-delivery (two
requests for the same `vapi_tool_call_id` both querying before either
commits) — that needs a database-level `INSERT ... ON CONFLICT` or a
serializable transaction, neither of which can be verified without a
real Postgres instance. Documented, not silently assumed away — see
`app/api/routes/vapi.py::_handle_one_tool_call`'s comment at the claim
site. The residual severity is low regardless: the actual booking
*mutation* underneath is independently protected by
`derive_idempotency_key()` + `IdempotencyStore` inside
`BookingService`/`CancellationService` — this table is audit
bookkeeping, not the mutation-safety mechanism, so the worst case is a
confusing log row, not a duplicate cancellation.

## Suggested system prompt (starting point, not final copy)

```
You are Charter123's voice booking assistant. You can search flights,
quote fares, and look up, create, modify, or cancel bookings using your
tools — never from memory or by guessing.

Before doing anything with an EXISTING booking beyond a public lookup
(modifying it, cancelling it, changing passengers, or reading back
details beyond basic status), call verify_booking_customer first: ask
for the confirmation number, then either the email or phone on the
booking, or a passenger's last name — ask for one of those, not both at
once. Keep the verification_token it returns and pass it to whichever
tool you call next for that booking.

Before cancelling, modifying, or removing a passenger from a booking,
read back exactly what will change (and any fee, for cancellations) and
wait for an explicit yes before calling the tool with
customer_confirmed set to true. A "yes" needs to be about the specific
change — don't infer confirmation from the caller just continuing the
conversation.

Never state a flight time, price, PNR, passenger detail, or booking
status that didn't come back from a tool call in this conversation. If
you don't have it, look it up or say you don't know.

If verification fails and can't be retried, if a caller asks for a
person, or if a request needs something outside your tools, call
transfer_to_human to log why, then immediately call the transfer tool to
connect them.
```

## Environment variables

Already present in `.env.example` (Phase 4 anticipated this phase):
`VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`, `VAPI_ASSISTANT_ID`,
`VAPI_PHONE_NUMBER_ID`. No new variables were needed.

## Multilingual voice — NOT IMPLEMENTED

No multilingual system prompt, language-detection strategy, or
per-language TTS/STT configuration exists. The suggested system prompt
above is English-only. If German or Persian support is required (both
plausible given Charter123's operating region), that needs: a
translated system prompt (or a language-detection instruction plus
per-language variants), a TTS/STT provider and voice selected per
language in the Vapi Assistant config, and an explicit fallback-language
rule so the agent doesn't silently switch languages mid-call on a
misheard word. None of this has been started, let alone verified — do
not configure a Vapi Assistant for production multilingual use based on
anything in this document.

## Testing status

**Verified locally (executed, 56 Phase-5-specific tests, part of a
179/179 full dependency-free run):** webhook shared-secret verification
(all header/case/priority variants), the tool schema <-> authorization
matrix consistency invariant, argument mapping and validation for every
implemented tool including the boolean-confirmation-coercion class of
bug, idempotency-key determinism, rate-limit keying, the
`FixedWindowRateLimiter`/`BackoffLockout` algorithms this phase depends
on (generic, not Vapi-specific — Phase 4's own tests already covered
these; Phase 5's tests confirm the specific profiles/keys used here
behave as expected against the same tested algorithm).

**Not executed, reviewed against verified interfaces only:**
`app/api/routes/vapi.py` itself, `app/api/deps_auth.py`'s
`redeem_verification_token()`, `Call`/`ToolExecution` models, migration
`0003`, and every path that requires FastAPI, SQLAlchemy, a real
Postgres, or a real Redis — none of which are installable in this build
environment (no network access).

**Environment-blocked entirely:** anything requiring a live Vapi
account, a live phone call, or a live webhook delivery.

## Known limitations (Phase 5, end of Phase 5.2)

- **`app/api/routes/vapi.py` and `app/api/deps_auth.py`'s
  `redeem_verification_token()` have never actually been run.** Reviewed
  carefully against verified method signatures; not executed. This is
  the single largest gap between "should work" and "known to work."
- **Transfer to human requires external Vapi configuration** (a native
  `transferCall` tool) that hasn't been created or tested — see above.
- **Rate-limit tuning is a placeholder**, not validated against real
  traffic — see the Rate limiting section's tuning caveat.
- **The concurrent (not sequential) double-delivery race on
  `ToolExecution.vapi_tool_call_id` is mitigated, not eliminated** — see
  the Idempotency section above.
- **No multilingual support** — see that section above.
- **`add_baggage`, `get_seat_options`, `select_seat`,
  `create_support_ticket`, `create_callback_request`,
  `create_payment_session`, `get_payment_status`** were INTENTIONALLY
  UNAVAILABLE at the end of Phase 5.2 — genuine domain gaps (no
  underlying model), not wiring gaps. Re-verified during Phase 5.2, not
  just carried forward as an assumption. **Update, Phase 6 Milestone 1:**
  `create_payment_session`/`get_payment_status` are now implemented — see
  the "Payments" section above and docs/PAYMENTS.md. The other five are
  unaffected by that milestone and remain unavailable for the same
  reason stated here.
- **No admin/staff UI exists to browse `Call`/`ToolExecution` rows** —
  the `calls.read`/`calls.manage` permissions this data is gated by
  already existed (Phase 4 anticipated this), but nothing renders them
  yet.
