# Charter123 — Phase 5 Engineering Handoff

**Read this entire document before modifying the repository.** It exists
so a new AI coding session — a different chat, possibly a different
model — can continue this project without re-deriving decisions already
made, re-discovering bugs already found and fixed, or re-litigating
architecture already settled. If something below conflicts with what you
observe in the repository, **trust the repository** and flag the
discrepancy; this document was written carefully against the actual
code, cross-checked line by line in most cases, but it is still prose,
not the source of truth.

---

## 1. Project identity

**Name:** Charter123 AI. **Purpose:** a production-grade charter/airline
booking platform with an AI voice-agent front end. **Product concept:** a
caller (phone, via Vapi) or a web visitor searches flights, gets a fare
quote, books, and can later look up, modify, or cancel that booking — all
through either a conversational voice agent or a conventional web app,
backed by the same authorization-hardened API. **Target users:**
individuals booking charter flights, plus human support/booking/finance
staff and admins operating the same system through role-gated tools.
**Current milestone:** Phase 5 of a 10-phase build.

**PHASE 5: COMPLETE** — *see §2 for exactly what that claim does and
does not mean.*
**PHASE 6: NOT STARTED.**

Provider-agnostic by design: the whole system runs against a
`MockAirlineProvider` with zero external aviation credentials; switching
to a real GDS (Amadeus/Sabre) is meant to be a config change, not a
rewrite (`docs/AIRLINE_PROVIDER.md`).

## 2. Executive status

**What is implemented and code-reviewed:** the entire voice-agent
integration described in §9-10 below — webhook authentication, rate
limiting, tool authorization, argument mapping for 14 real tools, the
`Call`/`ToolExecution` data model, and a shared (not duplicated)
verification-token redemption path between the web and voice channels.

**What is executed and passing:** the dependency-free core — 179 tests,
`python3 -m unittest tests.test_core_logic tests.test_security_core
tests.test_vapi_core -v`. This includes 56 tests written this phase
covering webhook auth, the tool-schema/authorization-matrix consistency
invariant, every implemented tool's argument mapping (including a real
bug this testing caught — see §12), and the rate-limiting/lockout
wiring.

**What is written but NOT executed:** `app/api/routes/vapi.py`,
`app/api/deps_auth.py`'s `redeem_verification_token()`, the `Call`/
`ToolExecution` SQLAlchemy models, migration `0003`, and
`tests/test_vapi_api.py` (an HTTP-level test file that skips cleanly,
exactly like Phase 4's `tests/test_api_security.py`, for the identical
reason: FastAPI/SQLAlchemy/pytest are not installable in this build
sandbox — no network access). These were reviewed against verified
method signatures (re-checked against the actual source repeatedly
during this phase, not assumed from an earlier reading), not guessed.

**What requires external verification and cannot be done here at all:**
a live Vapi account, a live phone call, `transfer_to_human`'s end-to-end
behavior (needs a Vapi-native `transferCall` tool configured in a
dashboard), and real-traffic validation of the rate-limit numbers
chosen.

**What is intentionally unavailable, not incomplete:** `add_baggage`,
`get_seat_options`, `select_seat`, `create_payment_session`,
`get_payment_status`, `create_support_ticket`, `create_callback_request`
— re-verified this phase (grepped every model file) that no underlying
domain model exists for any of these. This is a Phase 6+/7 scope
question, not a Phase 5 gap.

**"PHASE 5: COMPLETE" means:** every piece of implementation and
verification achievable inside this sandbox has been done, reviewed, and
is honestly labeled. It does **not** mean the webhook route has ever
handled a real HTTP request, or that a Vapi assistant has ever actually
called it. This is the same standard Phase 4 was declared complete
under (its own FastAPI/SQLAlchemy layer was equally unexecuted) — not a
lowered bar invented for this phase.

## 3. Complete architecture

```
Customer
   |
   v
Web  ─────────────────────────┐         Vapi Voice Agent
   |                           |               |
   v                           |               v (tool call)
Authentication            (same API)   POST /api/v1/vapi/webhook
   |                           |               |
   v                           |               v
Authorization  <────────────────────  authorize_vapi_tool_call()
   |                           |               |
   v                           v               v
Application Service (Booking/Cancellation/Passenger/Flight)
   |
   v
Repository  ──>  PostgreSQL
   |
   v
AirlineProvider  ──>  MockAirlineProvider / (future) Amadeus / Sabre
```

Voice path, in full, as actually built:

```
Phone Call
   v
Vapi (STT/LLM/TTS)
   v
POST {server_url}/api/v1/vapi/webhook
   v
1. verify_webhook_request()        — shared-secret check (401 if it fails)
2. webhook-level rate limit        — 429 if exceeded, by source IP
3. parse_tool_call_arguments()     — per tool call in the batch
4. BookingRepository.get_by_pnr()  — server-side truth, never trust an id
5. redeem_verification_token()     — raw token -> CurrentActor.verified_*
6. per-tool-call rate limit        — results[].error if exceeded, by call_id
7. authorize_vapi_tool_call()      — the ONE allow/deny decision
8. BookingService / CancellationService / PassengerService / FlightService
9. ToolExecution row (always) + AuditLog row (mutations, via the service)
   v
{"results": [{"toolCallId": "...", "result": "..."}]}   <- always HTTP 200
```

**Responsibility of every layer:**
- **Vapi** — speech in, speech out, decides *when* to call a tool. Never a source of truth, never an authorization authority, never allowed to invent a fact.
- **Webhook route (`app/api/routes/vapi.py`)** — authenticates the request, translates Vapi's JSON shape into the same request shapes the web API uses, and NEVER makes a business decision itself.
- **`app/core/security/*`** — the actual allow/deny decision (`authorize_vapi_tool_call`, `authorize_booking_access`), shared verbatim between web and voice.
- **Application services** — the only place booking/cancellation/passenger business logic lives, called identically by both channels.
- **Repositories/`AirlineProvider`** — persistence and the airline/GDS boundary.

## 4. Phase-by-phase history

### Phase 1-3
Repository/infra scaffold (monorepo: `apps/api`, `apps/web`, `docs/`).
FastAPI + SQLAlchemy + PostgreSQL(+SQLite fallback) + Redis(+in-process
fallback) backend foundation. `AirlineProvider` interface +
`MockAirlineProvider` (fully-featured, deterministic) + placeholder
Amadeus/Sabre adapters that fail loudly rather than fabricate. Flight
search, fare quotes, booking creation/lookup/modification/cancellation,
passenger management. PNR generation. Idempotency (application- and
provider-level). Audit logging. Passport field encryption. Reference
data (airports/aircraft).

### Phase 4 — Authentication, Authorization & Security
`User` model, Argon2id password hashing, full auth route set (register/
login/logout/logout-all/refresh/change-password/reset-password), opaque
hashed session tokens, RBAC (7 roles x 25 permissions, DB-backed),
customer ownership/IDOR prevention (`ownership.py`), booking verification
state machine + `/bookings/{pnr}/verify`, Vapi security *preparation*
(actor type + authorization matrix — architecture only, no webhook yet),
admin bootstrap, rate limiting + progressive lockout, CSRF, security
headers, centralized log redaction, extended audit logging, frontend auth
foundation. **123/123 dependency-free tests**, 4 real bugs found by
execution (IDOR from permission-check ordering, mutable dataclass
aliasing in the rate limiter, a `cryptography` version pin that excluded
the Argon2id feature the code actually used, an email-vs-local-part
password-policy bug) — full detail in this document's §12, carried
forward from `PROJECT_HANDOFF_PHASE_4.md`.

### Phase 5.1 — Vapi webhook foundation
Extended `TOOL_AUTHORIZATION_MATRIX` from 8 to 23 tools. Built
`app/core/security/vapi_webhook_auth.py` (shared-secret verification,
sourced against docs.vapi.ai, not guessed), `app/core/vapi/tool_schemas.py`
(JSON-schema registry for every tool) and `argument_mapping.py`
(Vapi-args-dict -> service-kwargs adapters, server-derived idempotency
keys). `Call`/`ToolExecution` models, repositories, migration `0003`.
The webhook route itself (`app/api/routes/vapi.py`), wired into
`main.py`. `docs/VAPI.md`. 44 new dependency-free tests — one real bug
caught by running them (see §12).

### Phase 5.2 — this phase: hardening, reconciliation, honesty pass
Wired the already-existing `vapi_webhook`/`vapi_tool` rate-limit profiles
into the webhook route (they existed since Phase 4, unused until now).
Wired a real `BackoffLockout` into Vapi-path booking verification
(`VerificationSessionService` already supported one; nothing had passed
it a real instance). Extracted `app/api/deps_auth.py::
redeem_verification_token()` — a genuinely pre-existing duplication
between `require_booking_access`/`require_passenger_access`, now a
single shared function all three call sites (including Vapi) use.
Partially closed the `ToolExecution` unique-constraint crash-recovery gap
(sequential retry now safe; concurrent double-delivery documented, not
silently assumed fixed). Fixed a misleading-confirmation issue in
`transfer_to_human` (it was claiming to move the call; it can't — only a
Vapi-native tool can). Corrected two documents (`docs/SECURITY.md` §7,
and this phase's own predecessor content) that oversold `VAPI_AGENT`'s
permission model. Re-verified, rather than assumed, that every
"unavailable" tool is a genuine domain gap. Added 12 more dependency-free
tests (rate-limit keying + the actual `FixedWindowRateLimiter`/
`BackoffLockout` behavior this phase depends on) and a new
`tests/test_vapi_api.py` HTTP-level file (skip-cleanly, same pattern as
`test_api_security.py`). **179/179 dependency-free tests.**

## 5. Current repository structure

```
charter123/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   │   ├── deps.py, deps_auth.py
│   │   │   │   └── routes/ (auth, aircraft, bookings, flights, health, passengers, vapi)
│   │   │   ├── core/
│   │   │   │   ├── config.py, exceptions.py, idempotency.py
│   │   │   │   ├── security/ (actor, csrf, errors, ownership, password_policy,
│   │   │   │   │   passwords, rate_limiter, rbac, redaction, tokens, verification,
│   │   │   │   │   vapi_authorization, vapi_webhook_auth)
│   │   │   │   └── vapi/ (argument_mapping, rate_limiting, tool_schemas)
│   │   │   ├── db/ (session.py, seed.py, migrations/versions/0001-0003)
│   │   │   ├── models/ (aircraft, airport, audit_log, base, booking, call,
│   │   │   │   customer, idempotency, rbac, session, tokens, tool_execution,
│   │   │   │   user, verification)
│   │   │   ├── providers/airline/ (base.py, mock.py, amadeus.py, sabre.py)
│   │   │   ├── repositories/ (booking, call, customer, rbac, session,
│   │   │   │   token, tool_execution, user, verification)
│   │   │   ├── schemas/ (booking, common, flight, passenger, ...)
│   │   │   └── services/ (audit_service, booking_service, cancellation_service,
│   │   │       flight_service, passenger_service, rate_limit_service,
│   │   │       verification_service)
│   │   ├── tests/ (test_core_logic, test_security_core, test_vapi_core,
│   │   │   test_api_security, test_vapi_api, voice/README.md)
│   │   └── requirements.txt
│   └── web/  (Next.js/TypeScript — auth foundation only, no voice-related UI)
├── docs/ (ARCHITECTURE, AIRLINE_PROVIDER, BOOKING_FLOW, ENVIRONMENT_VARIABLES,
│   PRODUCTION_CHECKLIST, SECURITY, VAPI)
├── infrastructure/, scripts/, tests/voice/
├── PROJECT_HANDOFF_PHASE_4.md
└── PROJECT_HANDOFF_PHASE_5.md  (this file)
```

## 6. Database state

**New this phase — `calls`:** `id` (UUID PK), `vapi_call_id` (unique,
indexed), `assistant_id`, `phone_number_id`, `direction`,
`customer_phone_number`, `status` (`in_progress`/`ended`),
`ended_reason`, `started_at`, `ended_at`, `created_at`/`updated_at`
(UTC). No FK to any other table — `vapi_call_id` is the join key
`AuditLog.call_id`/`VerificationSession.call_id` (both plain strings,
Phase 4) already use, intentionally not retrofitted into a real FK.

**New this phase — `tool_executions`:** `id` (UUID PK), `call_id` (real
FK -> `calls.id`, both new in this migration so no retrofit risk),
`vapi_tool_call_id` (unique, indexed — transport-level dedup, distinct
from business-level idempotency), `tool_name` (indexed),
`arguments_redacted` (JSON, redacted via
`app.core.security.redaction.redact_value` before storage),
`authorization_result` (`allowed`/`denied`), `denial_reason`, `outcome`
(`success`/`error`/`not_implemented`), `error_code`, `idempotency_key`
(indexed), `latency_ms`, `created_at` (UTC, no `updated_at` — append-only
like `AuditLog`, except for the documented crash-recovery reuse case in
§12).

**Migration `0003`**: statically reviewed against both models
column-for-column (matches exactly), and against migrations `0001`/`0002`
for style consistency (`sa.Uuid`, no explicit `ondelete` — matching the
existing convention of no cascades anywhere in this schema). **Not run**
— no Postgres in this sandbox.

**Unchanged this phase:** everything in `PROJECT_HANDOFF_PHASE_4.md` §6
(users, sessions, rbac tables, verification_sessions, password/email
tokens) and Phase 1-3's booking/customer/aircraft/airport/audit_log/
idempotency tables. The pre-existing, still-not-fixed
`customers.email` unique-constraint-missing-from-migration-0001 issue
(Phase 4 §5) remains exactly as documented there — out of scope for
Phase 5, unrelated to voice.

## 7. Authentication & authorization

Unchanged from Phase 4 for the web path — see `docs/SECURITY.md` and
`PROJECT_HANDOFF_PHASE_4.md` §6-7 for the full account (Argon2id,
sessions, RBAC, CSRF).

**Vapi-specific, built this phase:**
- **Authentication**: a shared secret (`VAPI_WEBHOOK_SECRET`), checked
  constant-time, against `X-Vapi-Secret` or `Authorization: Bearer`
  (`app/core/security/vapi_webhook_auth.py`). Fails closed if unset.
- **Authorization**: `authorize_vapi_tool_call()` (Phase 4, extended this
  phase from 8 to 23 matrix entries) — the ONE gate every tool call goes
  through. `VAPI_ASSISTANT_PERMISSIONS` (new this phase) is the
  structural bound on what a `VAPI_AGENT` actor can ever hold — built by
  excluding `STAFF_OR_ADMIN_ONLY` permissions from the matrix, not by a
  runtime check that could be forgotten. **Vapi is NEVER an
  authorization authority. Vapi must never bypass Charter123
  authorization or business rules.** This is enforced structurally
  (the webhook route cannot call a service without going through
  `authorize_vapi_tool_call` first — see `_handle_one_tool_call`), not
  just documented.
- **Booking verification for voice**: `verify_booking_customer` produces
  a token (`VerificationSessionService.start()`/`submit()`, unchanged
  Phase 4 machinery) scoped to the one fixed purpose `"vapi_tool_access"`
  (a deliberate, tested design — see `vapi_authorization.py`'s
  docstring — coarser than the web path's per-action purposes, but still
  scoped per-booking and still a genuine bearer-token requirement, not a
  bypass).
- **Reconciliation this phase**: `app/api/deps_auth.py::
  redeem_verification_token()` is now the ONE function that turns a raw
  token into an upgraded `CurrentActor`, used by the web path
  (`ANONYMOUS_VERIFIED`) and the voice path (`VAPI_AGENT`) alike — see
  §11 for the safety argument.
- **Rate limiting/lockout for voice**: see §9.

## 8. Booking domain

Unchanged lifecycle from Phase 1-4 (Search -> Quote -> Passenger Info ->
Booking -> Lookup -> Modification -> Cancellation). Phase 5 adds a
second, voice-native way to reach every step of it, through the same
`BookingService`/`CancellationService`/`PassengerService`/`FlightService`
— no booking logic was duplicated into the Vapi layer. Confirmation
requirements, idempotency, and authorization are all per §7/§9/§10.

## 9. Vapi/voice-agent implementation

**Full detail lives in `docs/VAPI.md`** — kept synchronized with this
document; that file is the one to read for the tool table, system
prompt, dashboard configuration steps, and the complete rate-limiting/
transfer-to-human/idempotency accounts. Summary:

- **Assistant config**: model/voice/STT/TTS unspecified (provider-
  agnostic by design); tools generated from
  `app.core.vapi.tool_schemas.as_vapi_function_definitions()`.
- **Phone numbers, inbound/outbound**: no code-level constraint either
  way; not configured or tested (external Vapi account required).
- **Webhooks**: one route, `POST /api/v1/vapi/webhook`, handling
  `tool-calls` (the real work) and `end-of-call-report` (captures
  `Call.status`/`ended_reason`); other message types get a bare 200
  acknowledgment.
- **Correlation**: Vapi's `call.id` -> `Call.vapi_call_id`; Vapi's
  per-tool-call `id` -> `ToolExecution.vapi_tool_call_id`.
- **Error handling**: every exception class the service layer can raise
  is caught in `_handle_one_tool_call` and turned into a
  `results[].error` string — never a stack trace, never a non-200 for a
  tool-specific problem.
- **Timeout/retry**: not implemented on the OUTBOUND side (this server
  never calls Vapi); Vapi's own retries of the INBOUND webhook are
  handled via the `ToolExecution` transport-level dedup (§12).
- **Transfer**: see `docs/VAPI.md` — PARTIALLY IMPLEMENTED, external
  verification required.
- **Recording/transcript, PII, multilingual**: not implemented — see
  `docs/VAPI.md`'s Known Limitations and Multilingual sections.

For every tool: name, purpose, authentication (shared secret, uniform),
authorization requirement, request/response shape, confirmation
requirement, idempotency behavior, and possible errors are all in
`docs/VAPI.md`'s tool table plus the docstrings in `tool_schemas.py`/
`argument_mapping.py` — not duplicated here to avoid the two drifting
apart, which is exactly the failure this phase found and fixed once
already (§12's Bug 7).

## 10. Voice safety rules

**The agent may (read-only, always available or after verification):**
search flights, check availability, get quotes/policies, retrieve
bookings (after verification), retrieve passenger information (after
verification).

**The agent must NOT execute without authentication + authorization +
confirmation:** booking creation, cancellation, modification, passenger
changes. All four require `authorize_vapi_tool_call()` to allow the
call; three of the four (modify, cancel, remove_passenger) additionally
require `customer_confirmed: true` as a literal boolean, enforced in
`app/core/vapi/argument_mapping.py` — a string `"true"` or an int `1`
does NOT satisfy this (tested,
`MutatingToolMappingTests.test_cancel_booking_rejects_truthy_non_boolean_confirmation`).

**The agent must NEVER invent** flight availability, prices, PNRs,
booking confirmations, passenger data, payment status, or airline
information. Architecturally true by construction: every dispatch
function in `app/api/routes/vapi.py` sources its result exclusively from
a service/repository/provider call — there is no code path where a
"result" string is built from anything other than a real query result.
The one thing that mitigates a still-real risk (a malicious/adversarial
string in provider or database data attempting to manipulate the LLM's
subsequent behavior — "prompt injection via tool results") is that this
architecture never lets the LLM's beliefs bypass the backend gates: even
if a manipulated tool result caused the LLM to *attempt* an unauthorized
action, `authorize_vapi_tool_call()`/confirmation checks still run
independently and would still deny it. Reviewed this phase (§11); no
code change was needed because the mitigation is structural, but this is
worth re-confirming if the LLM/prompt layer changes significantly.

## 11. Security review (Phase 5.2, full pass against the standard checklist)

- **Authentication bypass**: none found — the shared-secret check is the sole, unconditional gate before any parsing.
- **Authorization bypass / IDOR / privilege escalation**: none found — `authorize_vapi_tool_call()` is unconditionally on the path to every dispatch; `VAPI_ASSISTANT_PERMISSIONS` structurally excludes staff/admin permissions (verified empirically this phase — `payments.refund`/`vapi.configure` provably absent from the computed set); IDOR protection for voice rests on the same per-booking, per-purpose verification-token requirement as the web path, unchanged from Phase 4.
- **SSRF**: no outbound request to caller/LLM-controlled input exists anywhere in this phase's code.
- **Replay attacks**: mitigated by business-level idempotency (`derive_idempotency_key`) and the new transport-level `ToolExecution` dedup — see §12/Bug list and `docs/VAPI.md`'s Idempotency section for the residual concurrent-race caveat.
- **Webhook spoofing**: prevented by the shared-secret check (constant-time comparison).
- **Secret leakage**: empirically confirmed this phase — `redact_value()` turns `verification_token` into `[REDACTED]` before it reaches `ToolExecution.arguments_redacted`; grepped every new file for logging calls that could embed a secret — none exist.
- **PII leakage**: names/phone/email/PNR are deliberately NOT redacted in `ToolExecution` (matching the existing, pre-Phase-5 convention for staff-facing audit data) — a considered decision, not an oversight; passport numbers were never exposed as a Vapi tool parameter at all, by design, in either phase of Phase 5.
- **Tool injection**: not reachable — `_DISPATCH[tool_name]` is only ever reached for a `tool_name` that already passed `authorize_vapi_tool_call()`, which itself denies anything not in `TOOL_AUTHORIZATION_MATRIX`.
- **Prompt injection through tool responses**: a real, structural, but *mitigated* risk — see §10's account of why the architecture prevents it from becoming a security bypass even in the worst case.
- **Unsafe mutation execution / missing confirmation**: reviewed every mutating tool individually this phase — `cancel_booking`/`modify_booking`/`remove_passenger` all require a literal boolean `True`; `add_passenger` deliberately requires none (matches the original tool plan); `create_booking`'s confirmation is architecturally implicit (a specific `quote_id` reference) — documented, not silently assumed adequate.
- **Rate-limit bypass**: no meaningful bypass path for a non-secret-holding attacker (`call_id` is only usable as a key by someone who already defeated authentication, at which point rate-limit bypass is not the bigger problem).
- **Insecure logging / error leakage**: no file in this phase logs anything; every exception path returns a fixed, pre-written, user-safe string or an `AppError`/`ProviderError`'s own `.message` (a field that class's own contract guarantees is safe) — never `str(exc)` on a raw/unexpected exception.

**Authorization reconciliation (item explicitly requested this phase):**
`authorize_booking_access()` reads pre-set `CurrentActor` fields; it
doesn't take a raw token. Token redemption happens one layer up
(`deps_auth.py`), which only handled `ANONYMOUS_VERIFIED` before this
phase. Phase 5.1 resolved this with a local copy in `vapi.py`; Phase 5.2
reconsidered and extracted `app/api/deps_auth.py::
redeem_verification_token()` as one shared function for all three call
sites. Safety argument (also in that function's docstring): every
existing, Phase-4-tested call site only ever passes `ANONYMOUS_VERIFIED`
or a staff/`HUMAN_USER` actor type — for all of those, the function's
condition evaluates exactly as it did before this change. `VAPI_AGENT`
is a code path no Phase 4 test exercised, because nothing before Phase 5
ever constructed one. This change cannot alter the outcome of anything
already tested; it only makes a previously-impossible call newly
possible. `authorize_vapi_tool_call()` itself was deliberately NOT
merged with `authorize_booking_access()`/`authorize_passenger_access()`
— it's a wider check (handles PUBLIC/STAFF_OR_ADMIN_ONLY tools those two
don't know about) and unifying them would have been exactly the "large
refactor merely for elegance" this phase was told to avoid.

## 12. Bugs discovered and fixed

Carried forward from `PROJECT_HANDOFF_PHASE_4.md` §5 (bugs 1-4: the IDOR
permission-check-ordering issue, mutable dataclass aliasing in the rate
limiter, the `cryptography` version pin that excluded Argon2id, and the
password-policy email-vs-local-part check — full detail there, not
repeated here to avoid the two documents drifting on the same content).

**Bug 5 (Phase 5.1) — confirmation-check misclassified an omitted field
as a different error than an explicit `false`.** `map_cancel_booking()`/
`map_remove_passenger()` originally used `_require(args, ...,
"customer_confirmed")`, which raised `MISSING_ARGUMENT` when the field
was left out entirely — but raised the (more correct) `CONFIRMATION_
REQUIRED` when it was explicitly `false`. Both mean the same thing
("not confirmed") and should produce the same error. **Detected by**
running `tests/test_vapi_core.py` for the first time — two tests failed
with the wrong error code. **Fixed** by removing `customer_confirmed`
from the generic `_require()` check and handling it with one unified
`if args.get("customer_confirmed") is not True: raise
CONFIRMATION_REQUIRED` in each mutating mapper. **Impact:** UX/error-
message quality, not a security gap — the call was correctly rejected
either way; only the error classification was wrong. **Regression
test:** `MutatingToolMappingTests.test_cancel_booking_rejects_missing_confirmation`
et al. **Status:** fixed, tested.

**Bug 6 (Phase 5.1) — `PassengerService.add_passenger()` return-value
mismatch caught before it shipped.** `_dispatch_add_passenger()` was
initially written to read `passenger.first_name`/`.last_name` off the
method's return value, but that method returns the updated `Booking`,
not the passenger just added (confirmed by reading the actual service
source). **Detected by** deliberate self-review against the verified
signature before any test run — never actually executed in the buggy
form, since this file can't be executed here at all; documenting it
anyway because it's exactly the class of mistake execution would have
caught, and "written correctly" claims should show the process, not just
the conclusion. **Fixed** by capturing `first_name`/`last_name` from the
known input arguments instead of the return value. **Status:** fixed,
not independently testable without FastAPI/SQLAlchemy.

**Bug 7 (Phase 5.1, documentation) — a factually wrong permission-model
claim, repeated in two documents.** Both `PROJECT_HANDOFF_PHASE_4.md` §9
and `docs/SECURITY.md` §7 stated a `VAPI_AGENT` actor's permission set
"is always exactly `{'vapi.execute'}`" — but `TOOL_AUTHORIZATION_MATRIX`
requires tool-specific permissions (`flights.read`, `bookings.cancel`,
...) to ever pass its own permission check, and the tests' own
`_vapi_actor()` helper already granted a broader default set. No code
before Phase 5 had ever constructed a real `VAPI_AGENT` actor to notice
the discrepancy. **Fixed** by introducing `VAPI_ASSISTANT_PERMISSIONS`
(a real, structural bound — everything non-staff in the matrix, plus
`vapi.execute`) and correcting `docs/SECURITY.md` §7 to describe what
that constant actually guarantees. `PROJECT_HANDOFF_PHASE_4.md` itself
was left unedited (it's a frozen historical record of Phase 4 as it
stood); this document and `SECURITY.md` are the corrected account going
forward. **Status:** fixed (code) and corrected (docs).

**Bug 8 (Phase 5.2) — a misleading confirmation in `transfer_to_human`.**
The tool's result text originally said "Transferring you to a team
member now" — but nothing in a custom webhook tool can move a live Vapi
call; only a Vapi-native `transferCall` tool can. A caller told this
would reasonably believe a transfer was in progress when nothing was
happening. **Detected by** the security review this phase's brief
explicitly required, not by a test (there's no way to test "does this
text mislead a human" with `unittest`). **Fixed** by changing the result
to an instruction back to the assistant ("Escalation logged. Use the
transfer tool now...") and documenting the required Vapi-side
`transferCall` configuration in `docs/VAPI.md`. **Status:** fixed
(logging/wording); the underlying capability remains PARTIALLY
IMPLEMENTED — EXTERNAL VAPI VERIFICATION REQUIRED.

## 13. Environment & infrastructure

Unchanged from Phase 4 — Python 3.11-class stdlib (no new interpreter
requirement), PostgreSQL, Redis (optional — in-process fallback exists),
Node/Next.js for the frontend (untouched this phase), Docker/Alembic
status as documented in `PROJECT_HANDOFF_PHASE_4.md` §16/§18. New for
Phase 5: a publicly reachable HTTPS URL for the Vapi Server URL
(standard Vapi requirement, not Charter123-specific), and a Vapi account
with a configured Assistant + phone number.

## 14. Environment variables

No new variables this phase — `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`,
`VAPI_ASSISTANT_ID`, `VAPI_PHONE_NUMBER_ID` were already added to
`.env.example`/`app/core/config.py` in Phase 4, anticipating this phase.
See `docs/ENVIRONMENT_VARIABLES.md` for the full table (unchanged) and
`docs/VAPI.md` for what each Vapi-specific one is used for.

## 15. Testing status

**EXECUTED AND PASSING (179 tests):**
- `tests/test_core_logic.py` — 30 (Phase 1-4, unchanged)
- `tests/test_security_core.py` — 93 (Phase 4, unchanged, includes the
  original 8-tool `VapiAuthorizationTests`)
- `tests/test_vapi_core.py` — 56 (44 from Phase 5.1 + 12 from Phase 5.2:
  webhook auth, tool-schema/matrix consistency, argument mapping for
  every implemented tool, idempotency-key determinism, rate-limit
  keying, the `FixedWindowRateLimiter`/`BackoffLockout` algorithms this
  phase's wiring depends on)

**NOT EXECUTED (written, reviewed, skip cleanly rather than fail):**
- `tests/test_api_security.py` — Phase 4, 6 test classes
- `tests/test_vapi_api.py` — Phase 5.2, 2 test classes (webhook auth over
  real HTTP, one end-to-end `search_flights` flow, unknown-tool handling,
  duplicate-tool-call-id dedup)

**ENVIRONMENT-BLOCKED** (cannot be written in a way that would execute
here at all): anything requiring a live Vapi account or phone call.

Exact command and result, reproducible:
```
cd apps/api
python3 -m unittest tests.test_core_logic tests.test_security_core tests.test_vapi_core tests.test_api_security tests.test_vapi_api -v
# Ran 179 tests in ~0.2s — OK (skipped=8)
```
No test anywhere in this project has ever been represented as passing
without actually being run.

## 16. Known limitations (full list — also in `docs/VAPI.md`)

1. `app/api/routes/vapi.py` and `deps_auth.py::redeem_verification_token()` have never been executed against a real FastAPI app.
2. `transfer_to_human`'s end-to-end behavior needs a Vapi-native `transferCall` tool configured in a real Vapi dashboard — not done, can't be done here.
3. `RATE_LIMIT_PROFILES["vapi_webhook"]`/`["vapi_tool"]` are unvalidated placeholder numbers.
4. A genuinely *concurrent* (not sequential) double-delivery of the same `vapi_tool_call_id` could still race past the `ToolExecution` unique constraint — mitigated (the underlying booking mutation is independently idempotency-protected), not eliminated.
5. No multilingual (German/Persian) system prompt or STT/TTS configuration exists.
6. `add_baggage`/`get_seat_options`/`select_seat`/`create_payment_session`/`get_payment_status`/`create_support_ticket`/`create_callback_request` are intentionally unavailable — no domain model exists.
7. No admin/staff UI renders `Call`/`ToolExecution` data yet (the `calls.read`/`calls.manage` permissions gating it already existed from Phase 4).
8. A reverse proxy/load balancer in front of the API in production may need `X-Forwarded-For` handling for the webhook-level rate limit's source-IP key to be meaningful — not implemented (no deployment topology exists to test against).
9. Every Phase 4 known limitation not superseded above still applies (`docs/PRODUCTION_CHECKLIST.md`) — e.g. the `customers.email` migration/model mismatch (§6).

## 17. Production readiness

```
[x] Backend — implemented, unit-tested where dependency-free, unverified end-to-end
[x] Database schema/migrations — implemented, statically reviewed, unexecuted
[x] Authentication — implemented and tested (Phase 4, unchanged)
[x] Authorization — implemented and tested; extended + reconciled this phase
[x] Booking domain — implemented, unchanged this phase
[ ] Payments — not implemented (Phase 7 per roadmap)
[ ] Notifications — not implemented
[x] Vapi integration (code) — implemented, code-reviewed, unexecuted
[ ] Vapi integration (live) — requires external verification
[x] Webhook authentication — implemented and tested
[x] Rate limiting (voice path) — implemented, wired this phase; tuning unvalidated
[ ] Observability/monitoring — not implemented
[x] Logging — implemented; redaction verified (empirically, this phase) to cover secrets, not PII generally (by design)
[x] Secrets management — env-var based, unchanged from Phase 4; no secret found hardcoded or logged anywhere in Phase 5 code (checked)
[ ] Deployment (containers/orchestration) — not implemented
[ ] Backups/disaster recovery — not implemented
[x] Security review — performed this phase against the standard checklist (§11); one real issue found and fixed (Bug 8)
[ ] Privacy/compliance sign-off — not performed
[ ] Frontend voice-related UI — none exists (not required by Phase 5's scope)
```

Nothing above is marked "production-ready" merely because code exists —
only "implemented" (code complete, reviewed, some tier of testing) where
that's accurate.

## 18. Do-not-change architectural invariants

All of Phase 4's (`PROJECT_HANDOFF_PHASE_4.md` §20) still apply. Adding,
from this phase:

- Do not let `authorize_vapi_tool_call()`'s sensitivity check run *after* its permission check — sensitivity-first is what makes `VAPI_ASSISTANT_PERMISSIONS` being "too broad on paper" harmless (a staff permission accidentally present in that set still couldn't be exercised, because `STAFF_OR_ADMIN_ONLY` denies before permission is even checked).
- Do not give the Vapi assistant a custom tool for anything `send_confirmation`/`send_sms`/`send_email`-shaped — these are system-triggered side effects, never an LLM-invoked action, by design.
- Do not let `verify_booking_customer`'s tool schema expose a `purpose` parameter — the Vapi channel always verifies for the one fixed `"vapi_tool_access"` purpose; exposing it would create a parameter the mapping layer silently ignores.
- Do not treat `docs/VAPI.md`'s tool table as aspirational — `tests/test_vapi_core.py::ToolRegistryConsistencyTests` enforces that the schema registry and the authorization matrix can't drift from each other; keep it that way rather than hand-editing one without the other.
- Do not derive a mutating tool's `idempotency_key` from anything the LLM supplies — always `derive_idempotency_key(call_id, operation, payload)`, server-side.
- Do not have a custom webhook tool claim a live call transfer happened — only Vapi's native `transferCall` tool can move a call; a custom tool's result text should never imply otherwise (see Bug 8).
- Do not re-duplicate `redeem_verification_token()` — it is now the one place both channels redeem a token; if a third channel needs this, extend that function, don't copy it again.
- Do not silently mark an "intentionally unavailable" tool as implemented without first checking whether the underlying domain model actually changed (a new `Payment`/`SupportTicket`/seat-map model appearing in a future phase is exactly the trigger to revisit §9/`docs/VAPI.md`'s tool table).

## 19. Phase 6 starting point

**Objective (business):** turn the "intentionally unavailable" tools into
real ones, starting with whichever the business considers highest-value
— most likely payments (Stripe, already named as Phase 7 in the original
roadmap — worth confirming numbering hasn't shifted) or seat selection.

**Objective (technical):** for each capability chosen, build the actual
domain model (e.g. a `Payment` table + Stripe integration, or a seat-map/
inventory model) and application service FIRST, exactly the way booking/
cancellation/passenger services already exist — THEN add the
corresponding Vapi tool by flipping `implemented=True` in
`tool_schemas.py` and writing its argument mapper/dispatch function,
mirroring the pattern every already-implemented tool follows. Do not
build Vapi-specific logic for a capability that doesn't have a
non-Vapi (web-reachable) application service behind it first — that
would violate "Vapi tools must call the same application services used
by the web/API layer" for a capability that has no other caller to keep
that service honest.

**Prerequisites/dependencies:** a decision on which capability first;
for payments specifically, a Stripe account and webhook secret,
analogous to how Vapi's own credentials work.

**Risks:** payment integration is a materially higher-stakes surface
than anything built so far (real money, PCI-adjacent concerns) — treat
it with at least the rigor this phase applied to authorization, probably
more.

**What must be inspected first:** this document in full, then
`docs/VAPI.md`, then the actual `app/core/vapi/tool_schemas.py` and
`app/api/routes/vapi.py` to confirm nothing has drifted from what's
described here. Run `tests.test_core_logic tests.test_security_core
tests.test_vapi_core` and confirm 179/179 before writing any code.

**First tests to run:** the exact command in §15.

**Proposed execution order:**
```
PHASE 6
  v
Milestone 1 — choose + build the domain model (e.g. Payment) + web-reachable service
  v
Milestone 2 — add the Vapi tool on top of that service (schema + mapper + dispatch)
  v
Milestone 3 — get the FastAPI/SQLAlchemy stack actually installed and run
              tests/test_api_security.py + tests/test_vapi_api.py for real —
              this has been deferred since Phase 4 and is overdue
  v
Integration Verification — a real Vapi account, a real test call
  v
Security Verification — repeat §11's checklist against whatever Milestone 1/2 added
  v
Regression Tests — full dependency-free suite + the now-executable HTTP suite
  v
Final Handoff — PROJECT_HANDOFF_PHASE_6.md
```

## 20. Next-AI instructions

You are continuing development of Charter123. This document is the
authoritative Phase 5 handoff.

1. Read this entire handoff.
2. Inspect the actual repository.
3. Compare the repository against this handoff — run
   `python3 -m unittest tests.test_core_logic tests.test_security_core
   tests.test_vapi_core -v` and confirm 179/179 before anything else.
4. Do not blindly trust this handoff if the code contradicts it — the
   repository is the source of truth, this document is prose written
   against it at a point in time.
5. Do not rebuild Phases 1-5 — they are frozen.
6. Do not start Phase 6 implementation until you've read `docs/VAPI.md`
   and confirmed the tool-completion state hasn't changed.
7. Preserve every invariant in §18.
8. If you get FastAPI/SQLAlchemy/pytest installed (network access this
   sandbox didn't have), running `tests/test_api_security.py` and
   `tests/test_vapi_api.py` for real is the single highest-value thing
   you can do before writing any new code — it would convert this
   phase's largest caveat ("never executed") into either a confirmed
   pass or a real, fixable bug report.
9. At the end of Phase 6, produce a complete project archive and
   `PROJECT_HANDOFF_PHASE_6.md`, held to the same "never claim untested
   things are tested" standard this document and its predecessor were.

## 21. Phase 5 changelog

**Phase 5** — 2026-09-04/05 (5.1 then 5.2, same overall phase)

**Major additions:** Vapi webhook route and full tool-call handling for
14 tools; `Call`/`ToolExecution` models + migration; webhook shared-secret
auth; tool JSON-schema registry; argument-mapping layer with server-side
idempotency-key derivation; rate limiting (webhook + per-call) and
booking-verification lockout, both newly wired onto Phase-4-built
infrastructure; a shared (de-duplicated) verification-token redemption
path across web and voice.

**Major changes:** `TOOL_AUTHORIZATION_MATRIX` 8 -> 23 entries;
`app/api/deps_auth.py` refactored (extract-method, not a rewrite) to
share token redemption across three call sites instead of two.

**Security changes:** `VAPI_ASSISTANT_PERMISSIONS` introduced as a
structural (not runtime-checked) bound on voice-agent capability;
`docs/SECURITY.md` §7 corrected; `transfer_to_human` corrected to never
imply a transfer that hasn't happened; a full security-checklist review
performed (§11).

**Database changes:** two new tables (`calls`, `tool_executions`),
migration `0003`, both statically reviewed, not executed.

**Vapi changes:** this entire phase.

**Tests:** 123 (Phase 4) -> 179 dependency-free (+56), plus a new
skip-cleanly HTTP test file (`test_vapi_api.py`, 2 classes, mirroring
`test_api_security.py`'s established pattern).

**Known limitations:** §16 above, in full.

**Next phase:** Phase 6 — see §19.
