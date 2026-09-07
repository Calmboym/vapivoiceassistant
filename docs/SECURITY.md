# Security Architecture

Phase 4 status. See `docs/PRODUCTION_CHECKLIST.md` for the line-by-line
implemented/tested/not-tested breakdown — this file explains the *design*;
that one tracks *verification status*.

## 1. Authentication architecture

```
Browser
  -> HTTP-only, Secure(prod), SameSite=Lax session cookie (c123_session)
  -> app/api/deps_auth.py::get_current_actor  (the ONLY place a request
     becomes a CurrentActor — reads the cookie, nothing else)
  -> CurrentActor  (app/core/security/actor.py)
  -> RBAC / ownership checks (app/core/security/{rbac,ownership}.py)
  -> Application service
```

Client-supplied identity headers (`x-user-id`, `x-admin-id`, `userId`,
`customerId`, or anything similar) are never read as identity anywhere in
this codebase. `CurrentActor`'s constructor has no field such a value could
flow into — see `tests/test_security_core.py::CriticalSecurityTest` for a
simulated attack that proves forged headers change nothing.

Passwords are hashed with **Argon2id**, via `cryptography`'s native
`Argon2id` KDF (`app/core/security/passwords.py`) — not `argon2-cffi`,
which this build sandbox cannot install; `cryptography` already ships as a
dependency (Fernet field encryption) and added a native Argon2id binding in
**version 44.0.0**. This is a hard dependency with no silent weaker
fallback: if it can't be imported, the app should fail to start, not
quietly hash passwords some other way — same "fail loudly, don't fabricate"
principle already applied to the airline provider adapters.

## 2. Session management

- `app/models/session.py`: only `session_token_hash` (SHA-256 of a 256-bit
  random token) is persisted. The raw token lives in the cookie and briefly
  in server memory during login/refresh — never in the database, never in a
  log line (see §9 redaction).
- `POST /auth/refresh` **rotates** the token (new random value, new stored
  hash) rather than just extending `expires_at` on the same one — bounds
  how long a stolen-but-unused cookie stays useful even if the legitimate
  user keeps refreshing.
- `POST /auth/logout` revokes one session; `POST /auth/logout-all` revokes
  every session for the user (`revoked_at` set, checked on every lookup).
  Password change and (architecturally) admin-disabling an account both
  call the same revoke-all path.
- Session token hashing uses **unsalted SHA-256**, not Argon2id — this is
  deliberate, not an inconsistency: the input is already a 256-bit random
  value with no guessable structure, so a slow password KDF adds CPU cost
  with no security benefit. The same reasoning applies to CSRF, booking
  verification, and password-reset tokens (see `app/core/security/tokens.py`).

## 3. Identity model: User vs. Customer

`User` (Phase 4) is a login-capable identity. `Customer` (Phase 1-3) is a
booking-contact record created ad-hoc, with no password, the moment
anyone — logged in or not — books a flight. These stay separate on
purpose: a caller can still book without ever creating an account (Vapi's
whole point), and a `User` optionally links to one `Customer` via
`User.customer_id` once they register. Staff/admin `User`s never get a
`customer_id` at all. `CurrentActor.customer_id` — never a request-supplied
value — is what every ownership check compares against.

## 4. RBAC

Roles: `CUSTOMER, SUPPORT_AGENT, BOOKING_AGENT, FINANCE, ADMIN, SUPER_ADMIN,
READ_ONLY`. Permissions are the flat `resource.verb` strings from the spec
(`bookings.cancel`, `payments.refund`, `admin.manage`, ...). The
role -> permission matrix lives in `app/core/security/rbac.py`
(`ROLE_PERMISSIONS`), pure and unit-tested; `app/db/seed.py::seed_rbac()`
loads it into the `roles`/`permissions`/`role_permissions` tables, which are
authoritative at runtime (`RBACService`/`RbacRepository`).

Authorization never checks a role name alone — see the bug this exact
shortcut caused, §11 below.

## 5. Customer ownership / IDOR prevention

`app/core/security/ownership.py` is the single place every "can this actor
touch this resource" decision gets made. It takes a `CurrentActor` and a
resource's *actual* owner id (loaded from the DB by primary key/PNR) — it
has no parameter a client-supplied id could occupy.

```python
def authorize_resource_access(actor, *, resource_customer_id, staff_permission, ...):
    if actor.actor_type == HUMAN_USER:
        is_owner = actor.customer_id == resource_customer_id   # session-derived, never request-derived
        if is_owner:
            return ALLOW if actor.has_permission(staff_permission) else DENY
        if actor.is_staff and actor.has_permission(staff_permission):
            return ALLOW   # staff access
        return DENY
    ...
```

### The bug this ordering fixes (found by execution, not inspection)

An earlier version of this function checked "does the actor hold
`staff_permission` at all" **before** checking ownership. Since the
`CUSTOMER` role also grants `bookings.read`/`bookings.cancel`/etc. (a
customer needs that permission for their *own* bookings), that first check
returned `ALLOW` for **any** authenticated customer against **any other**
customer's booking — a real IDOR hole, caught by
`tests/test_security_core.py::CriticalSecurityTest` actually failing on a
first run, not by code review. The fix: check ownership first, and gate
non-owner access on `actor.is_staff` (any role beyond bare `CUSTOMER`) *in
addition to* the permission — never permission-string membership alone.
Full writeup: `PROJECT_HANDOFF_PHASE_4.md` §5.

### Information-disclosure policy

- Unknown PNR: `404 BOOKING_NOT_FOUND` (unchanged from Phase 1-3).
- Anonymous/voice caller without a completed verification: `403
  BOOKING_VERIFICATION_REQUIRED` (matches the existing lookup endpoint's
  Phase 1-3 behavior — cancel/modify now enforce the same rule, closing the
  gap described in §7).
- Authenticated customer against a booking that exists but isn't theirs:
  `403` or `404` depending on route (booking mutation routes return
  whatever `authorize_booking_access` yields — see code comments in
  `app/api/routes/bookings.py` for the exact per-route choice and the PNR-
  enumeration trade-off behind it).

## 6. Booking verification (§12)

State machine (`app/core/security/verification.py`, pure, immutable
dataclass — each transition returns a new instance, not a mutated one; see
§10 lesson-learned below for why that matters):

```
VERIFICATION_PENDING --(factor matched)--> VERIFIED
VERIFICATION_PENDING --(factor wrong, attempts < max)--> VERIFICATION_PENDING
VERIFICATION_PENDING --(factor wrong, attempts >= max)--> FAILED
VERIFICATION_PENDING --(expires_at passed)--> EXPIRED
```

A token is scoped to exactly one `(call_id, booking_id, purpose)` triple —
`VerificationSessionService.check()` requires all three to match, not just
"is there a VERIFIED session somewhere for this token". `purpose` matters
specifically: a token verified for `"view_booking"` does not authorize
`"cancel_booking"`.

**The gap this closes**: Phase 1-3's `cancel_booking`/`modify_booking`
routes accepted only a client-supplied `customer_confirmed: bool` — a UX
consent flag ("customer said yes to the fee"), not identity proof, but it
was the *only* gate. Phase 4 adds `POST /bookings/{pnr}/verify`
(email/phone + last-name factor check -> short-lived token) and requires
that token — or authenticated ownership, or staff permission — before
`cancel`/`modify`/passenger-mutation routes will act. `customer_confirmed`
is untouched; it's still checked, just no longer alone.

For the future Vapi call: `call_id` scoping means a verification completed
during one phone call can't be replayed by a different call that happens to
guess the token format, and the token itself (not just "is *a* session
VERIFIED") is what's actually checked — see
`tests/test_security_core.py::VerificationSessionTests`.

## 7. Vapi security preparation (§13/§14) — Phase 4 architecture; Phase 5 built the webhook handler

`ActorType.VAPI_AGENT` is a distinct actor type from `HUMAN_USER`. Its
permission set is bounded by `VAPI_ASSISTANT_PERMISSIONS`
(`app/core/security/vapi_authorization.py`, added in Phase 5) — it can
never carry `admin.manage`, `payments.refund`, `vapi.configure`, or any
other `STAFF_OR_ADMIN_ONLY` permission, by construction (that constant is
built by excluding exactly that category from
`TOOL_AUTHORIZATION_MATRIX`, not by a runtime check that could be
forgotten), even though it does need more than the single literal
`"vapi.execute"` string to exercise any PUBLIC or
REQUIRES_VERIFIED_BOOKING tool at all.

*(Correction, Phase 5: this section previously stated the permission set
is "always exactly `{\"vapi.execute\"}`". That undersold what the matrix
below actually requires — a real `CurrentActor(actor_type=VAPI_AGENT)`
needs `flights.read`/`bookings.cancel`/etc. for `authorize_vapi_tool_call()`'s
permission check to ever pass, and nothing before Phase 5 had constructed
one to notice. The property this sentence was actually protecting — a
voice agent can never become staff or admin — is unchanged and is what
`VAPI_ASSISTANT_PERMISSIONS` now guarantees structurally. See
`PROJECT_HANDOFF_PHASE_4.md`'s Phase 5 successor for the full account.)*

`app/core/security/vapi_authorization.py`'s `TOOL_AUTHORIZATION_MATRIX`
(23 entries as of Phase 5, up from Phase 4's original 8) classifies every
tool as `PUBLIC`, `REQUIRES_VERIFIED_BOOKING`, or `STAFF_OR_ADMIN_ONLY`
(the last category always denies a Vapi actor — see
`authorize_vapi_tool_call()`). This is unit-tested, in
`tests/test_security_core.py::VapiAuthorizationTests` (Phase 4, the
original 8 tools) and `tests/test_vapi_core.py::ToolRegistryConsistencyTests`
(Phase 5, the full 23) — specifically so the rule "the LLM is never an
administrator" is enforced by code, not a system prompt.

Phase 5 built the actual webhook handler
(`app/api/routes/vapi.py`) that constructs a `CurrentActor(actor_type=
VAPI_AGENT, ...)` from a **verified webhook shared secret**
(`app/core/security/vapi_webhook_auth.py`) and hands it to
`authorize_vapi_tool_call()` for every tool call — it never decides "is
this allowed" itself, and the Vapi assistant's system prompt is never
treated as an authorization mechanism (see `docs/VAPI.md`). This file has
not been executed against a real FastAPI app or a live Vapi call in this
sandbox (no network access to install FastAPI/SQLAlchemy) — see
`docs/VAPI.md`'s Known Limitations for exactly what is and isn't
verified.

## 8. Rate limiting & account lockout (§17/§18)

`app/core/security/rate_limiter.py`, pure, against a tiny `RateLimitStore`
Protocol (same pattern as `app.core.idempotency`'s store split) so the
algorithm is unit-tested without Redis. `app/services/rate_limit_service.py`
adapts it onto `app.db.redis_client.get_redis()` — real Redis, or the
existing in-process fallback when `REDIS_URL` is unset.

- `FixedWindowRateLimiter`: N requests per window per key. Profiles for
  login, register, password-reset-request, booking-lookup,
  booking-verification (tightest — 5/10min, the actual guessing-resistance
  boundary), vapi-webhook, vapi-tool, admin-login.
- `BackoffLockout`: progressive per-*account* lockout after repeated auth
  failures (30s -> 2min -> 15min -> 1hr, capped), separate from the
  per-endpoint limiter above — protects one account against a distributed
  brute force spread across many IPs, which per-IP limiting alone wouldn't
  catch. Never permanent.

**Phase 5 addendum:** the `vapi-webhook`/`vapi-tool` profiles referenced
above were defined in Phase 4 but not wired into anything until Phase 5.
`app/api/routes/vapi.py` now checks `vapi_webhook` per source IP on every
webhook POST (a non-200 rejection, same footing as the shared-secret
check) and `vapi_tool` per Vapi `call_id` on every individual tool call
within it (a `results[].error` entry, since Vapi expects one per tool
call regardless — see `docs/VAPI.md`). `VerificationSessionService` also
now receives a real `BackoffLockout(RedisRateLimitStore())` from the Vapi
path (`app/api/routes/vapi.py::_verification_lockout()`) — previously
only the web `/bookings/{pnr}/verify` route passed one in; the Vapi path
called the service with no rate limiter at all, so repeated wrong-answer
guessing against a booking via that channel specifically was unbounded
(the underlying attempt-count state machine still capped it, per-session,
at `DEFAULT_MAX_ATTEMPTS`, but a caller could just start a fresh session
and try again indefinitely without this). New keying policy in
`app/core/vapi/rate_limiting.py`, tested in
`tests/test_vapi_core.py::RateLimitKeyingTests`/`VapiRateLimitProfileWiringTests`.

### Lesson learned: mutable state and "the same object, mutated twice"

`BackoffLockout.record_failure()` originally returned the `FailureState`
object it had just mutated — but `InMemoryRateLimitStore` returns the same
object reference on every `get`/`set` round-trip, so two successive
`record_failure()` calls in a test both ended up holding **the same,
further-mutated object**, making "backoff increases with each failure" look
false even though the underlying counting was correct. Fixed by returning
`dataclasses.replace(state)` — a snapshot — instead of the live reference.
Same root cause, different flavor, as the ownership-ordering bug in §5: code
that *looked* right on inspection, wrong when actually run. Full writeup:
`PROJECT_HANDOFF_PHASE_4.md` §5.

## 9. CSRF (§19)

Signed double-submit cookie, bound to the session id (stronger than plain
double-submit — see `app/core/security/csrf.py`'s module docstring for why
binding to the session matters). `c123_csrf` is deliberately **not**
`HttpOnly` — the frontend JS has to read it and echo it in the
`X-CSRF-Token` header; that's the entire mechanism. Enforced by
`app/middleware/csrf.py` on every state-changing (POST/PUT/PATCH/DELETE)
request that carries the session cookie. A request with **no** session
cookie (Vapi webhooks, any future bearer-token server caller) is exempt —
CSRF specifically attacks cookie-riding, so a caller not using the cookie
at all has nothing for it to protect. `/auth/login`, `/register`,
`/request-password-reset`, `/reset-password` are exempt for the same
reason a login form can't require a CSRF token bound to a session that
doesn't exist yet — protected by rate limiting instead.

## 10. CORS

`CORS_ORIGINS` (comma-separated, `app/core/config.py`) — never `["*"]` with
credentials, which FastAPI/Starlette actually refuses to do at the
protocol level anyway when `allow_credentials=True`. Configured in
`app/main.py` from `settings.cors_origin_list`; unchanged from Phase 1-3,
audited and confirmed correct as part of this phase rather than rebuilt.

## 11. Security headers (§21)

`app/middleware/security_headers.py`: `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
a strict `Content-Security-Policy: default-src 'none'` (loosened only for
FastAPI's own `/docs`/`/redoc`), and `Strict-Transport-Security` when
`APP_ENV=production`.

## 12. Secret management (§22)

Everything comes from environment variables, read in exactly one place
(`app/core/config.py::Settings`) — see `docs/ENVIRONMENT_VARIABLES.md`.
`.env` is gitignored; `.env.example` has placeholders only.
`Settings.validate_for_production()` fails fast at startup if
`APP_ENV=production` and anything required is missing — Phase 4 adds one
more check to that list: `BOOTSTRAP_ADMIN_ENABLED` must be `false` in
production.

## 13. Passport encryption audit (§23)

Audited, not rewritten (Phase 1-3 code, unchanged): `app/core/encryption.py`
uses Fernet (`cryptography`) with the key from `FIELD_ENCRYPTION_KEY`, no
hard-coded key, and an explicit `UNENCRYPTED-DEV:`-prefixed fallback with a
logged warning when the key is unset — deliberately awkward so it can't
quietly ship to production unencrypted. Decrypted passport values are only
materialized where actually needed (`mask_for_speech` for anything a Vapi
response might read back); normal customer-facing responses never include
the raw field. Passport-mutation routes (`POST /passengers/{pnr}/{id}/passport`)
now carry the same authorization bar as booking cancel/modify (§6/§7) —
previously they had none.

## 14. Log redaction (§24)

`app/core/security/redaction.py` — pure, recursive, key-pattern-based
(`password`, `secret`, `token`, `api_key`, `passport`, `authorization`,
`cookie`, `session`, `stripe`, `vapi_*`, and more — see
`SENSITIVE_KEY_PATTERN`). `app/core/logging.py`'s existing `_redact_processor`
(Phase 1-3, structlog-coupled) now delegates to this shared function instead
of keeping its own smaller inline pattern — one list of "what's sensitive",
not two that can drift apart. Real, executed tests in
`tests/test_security_core.py::RedactionTests` cover nested dicts and
lists-of-dicts, and confirm key-match is checked *before* recursing (a
`{"payment_secret": {"raw": "..."}}`-shaped value is redacted wholesale, not
leaked because the inner key `"raw"` doesn't itself look sensitive).

## 15. Audit logging (§25)

Extended, not duplicated: the existing `AuditLog` model/`record_audit_event()`
(Phase 1-3) already had the right shape (`actor`, `actor_type`, `action`,
`resource`, `resource_id`, `request_id`, `call_id`, `event_metadata`) for
auth events too — no new `SecurityEvent` table. New `action` values:
`auth.registered`, `auth.login_succeeded`, `auth.login_failed`,
`auth.login_blocked_suspended`, `auth.login_blocked_disabled`,
`auth.password_changed`, `auth.password_reset_requested`,
`auth.password_reset_completed`, `auth.session_created`,
`auth.session_revoked`, `auth.all_sessions_revoked`, `rbac.role_assigned`,
`rbac.role_revoked`, `bootstrap.admin_created`/`admin_promoted`. New
`actor_type` values `user` (auth lifecycle, privilege-tier-agnostic) and
`admin` (privileged mutations), alongside Phase 1-3's existing `customer`/
`ai_agent`/`system`. Every `AuthService`/`SessionService` method that
writes an audit row commits in the same call, matching the existing
Phase 1-3 convention (`self.db.commit()` right after
`record_audit_event(...)`, not left to the route).

## 16. Request correlation (§26)

`request.state.request_id` (Phase 1-3's existing middleware, unchanged) now
also threads through every Phase 4 service call and audit-log row, so an
auth event and the HTTP request that caused it correlate the same way a
booking mutation and its audit row already did.

## 17. Error codes (§27)

`app/core/security/errors.py::AuthErrorCode` — the fixed vocabulary from the
spec, plus `WEAK_PASSWORD`/`CSRF_FAILED`/`INVALID_TOKEN` where the spec's
list was clearly non-exhaustive. `app/core/exceptions.py::AuthError` derives
its HTTP status automatically from `HTTP_STATUS_FOR_CODE` rather than each
call site having to remember which of `NotFoundError`/`ForbiddenError`/
`UnauthorizedError`/... happens to match a given code — see
`PROJECT_HANDOFF_PHASE_4.md` §5 for the mismatch this replaced.

## 18. Enumeration trade-offs

- **Login / password reset**: always the same generic response regardless
  of whether the email exists (§18/§28).
- **Registration**: the one boundary that *does* say "this email is already
  registered" — required for the flow to be usable, and doesn't leak
  anything an attacker couldn't already learn by attempting the same
  registration themselves.
- **Booking lookup/mutation**: see §5's information-disclosure policy.

## 19. GDPR-sensitive data handling

Not newly solved in this phase. Existing Phase 1-3 retention settings
(`CALL_TRANSCRIPT_RETENTION_DAYS`, `AUDIT_LOG_RETENTION_DAYS`, etc.) remain
defined but unenforced (no cleanup job). `AuditLog`/`Session`/
`VerificationSession` rows now hold more personally-identifying data
volume than before this phase (every login, every verification attempt);
a GDPR export/deletion endpoint (§66) is explicitly out of scope for
Phase 4 and listed as a known gap in `docs/PRODUCTION_CHECKLIST.md`. This
needs human/legal review before a production launch that handles EU
personal data — not something to infer from code comments alone.

## 20. Incident-response considerations (not implemented, noted for awareness)

- Revoking a compromised `SECRET_KEY`: rotate it; every outstanding CSRF
  cookie becomes invalid immediately (browsers just get a fresh one on
  their next response), sessions are unaffected (looked up by their own
  stored hash, independent of `SECRET_KEY`).
- Revoking a compromised session: `SessionService.revoke()` /
  `revoke_all_for_user()` — immediate, no waiting for natural expiry.
- Suspending an account mid-session: setting `User.status = "SUSPENDED"`
  is checked on the *next* request via `get_current_actor` (fails closed to
  `ANONYMOUS_VERIFIED` if the user is disabled/deleted) and explicitly in
  `require_authenticated_user` for suspended; there is no active
  session-invalidation push — a already-open request that read the actor
  before the status change completes normally. Acceptable for this
  phase's threat model; a real-time kill-switch would need a
  pub/sub-invalidated in-memory cache and is out of scope here.
- No alerting/paging is wired to any of `RATE_LIMITED`, repeated
  `auth.login_failed` rows, or `BOOKING_VERIFICATION_FAILED` events —
  they're recorded (§15) but nothing currently watches them.

## 21. Known limitations of this phase

- No admin dashboard exists yet to actually *use* `ADMIN`/`SUPER_ADMIN`
  permissions through a UI — only the backend authorization boundary and
  `bootstrap_admin.py` exist.
- Email verification tokens (`EmailVerificationToken` model,
  `MockEmailProvider`) are modeled and the schema exists, but no route
  issues/consumes an email-verification token yet (`email_verified` stays
  `False` after registration) — `POST /auth/register` was in the spec's
  required endpoint list and is implemented; the *verify* endpoint wasn't
  in that list and wasn't added speculatively.
- The FastAPI/SQLAlchemy layer (everything except
  `app/core/security/*.py`) has not been executed in this build
  environment — no network access to install fastapi/sqlalchemy/pydantic.
  See `docs/PRODUCTION_CHECKLIST.md` and `PROJECT_HANDOFF_PHASE_4.md` §4/§17.

## 22. Payment authorization (Phase 6 Milestone 1)

`authorize_payment_access()` (this file's §5 territory) predates any
payment backend — it was written in Phase 4 with no
`verification_purpose` parameter at all, so it structurally can never be
satisfied by a verification-token-only actor (`ANONYMOUS_VERIFIED`/
`VAPI_AGENT`), regardless of which `payments.*` permission is requested.
Phase 6 Milestone 1 built on top of that unchanged: two different
authorization gates converge on one `PaymentService`, exactly like
`BookingService` already has for the rest of the booking lifecycle —

- **Web** (`app/api/routes/payments.py`): `require_payment_access()` ->
  `authorize_payment_access()` — authenticated owner or FINANCE/ADMIN
  staff, never a token.
- **Voice** (`app/api/routes/vapi.py`): the already-registered
  `REQUIRES_VERIFIED_BOOKING` matrix entries for
  `create_payment_session`/`get_payment_status` — the SAME gate
  `cancel_booking`/`modify_booking` already use. Unchanged from Phase 5;
  no matrix edit was needed for this milestone.

Full reasoning, the domain model, state machine, idempotency guarantees,
and the Stripe webhook trust boundary are in **docs/PAYMENTS.md** rather
than duplicated here. Test:
`tests.test_security_core.OwnershipTests.
test_payment_access_denies_a_vapi_agent_for_create_and_read_too` pins
this design decision — added this milestone specifically because the
two-gate split isn't obvious from reading either function in isolation.
