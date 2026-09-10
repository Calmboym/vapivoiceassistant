# Handoff: T-5 — Phase 8: notifications

## 1. Current project position

Phases 1–5 complete (repo/infra → DB schema & mock provider → core
booking flows → authentication/RBAC/security → Vapi voice integration).
Phase 7 Milestone 1 (Stripe payment sessions, labeled "Phase 6
Milestone 1" in its own handoff — see `docs/PROJECT_ROADMAP.md` §6.1)
and `refund_payment` (T-3, 2026-09-08) are done. `scripts/setup_vapi.py`
(T-4, 2026-09-09, earlier the same day) is written and tested but never
run against a live Vapi account. This session (T-5, 2026-09-09) built
Phase 8: real email (Resend) and SMS (Twilio) providers, wired to
booking-confirmation and payment-link delivery. Admin dashboard
(Phase 9) and the Playwright/E2E/voice test suites (Phase 10) remain
entirely unbuilt. T-1 (install the real dependency stack and run the
FastAPI/SQLAlchemy-level suites) remains blocked in every sandbox this
project has used, this one included — re-confirmed this session.

## 2. Completed work

- Designed and implemented a dependency-free content-building module for
  both notification types, deliberately isolated from SQLAlchemy so its
  logic — the part most likely to leak something it shouldn't (a
  passport number) or invent something it doesn't know (a cancellation
  fee, a baggage figure) — gets real, executed test coverage in this
  sandbox.
- Extended `EmailProvider` with two new methods
  (`send_booking_confirmation`/`send_payment_link`) without touching the
  two original ones; added `ResendEmailProvider`.
- Designed a new `SmsProvider` interface (none existed before this
  task), mirroring `EmailProvider`'s shape; added `MockSmsProvider` and
  `TwilioSmsProvider`.
- Built `NotificationService`, a new orchestration layer that converts
  ORM objects to the content module's plain dataclasses, dispatches to
  whichever provider it's constructed with, and audits every outcome —
  designed from the start to be best-effort and non-blocking, and to
  never be reachable as a Vapi tool (MASTER_RULES §6).
- Wired `NotificationService` into exactly two call sites —
  `BookingService.create_booking` and
  `PaymentService.create_payment_session` — via an *optional* constructor
  parameter, deliberately choosing not to touch any other
  `BookingService`/`PaymentService` construction site (including
  `CancellationService`'s internal one).
- Updated the `create_payment_session` Vapi tool's description and its
  dispatch function's return string, since the tool no longer needs to
  tell the assistant delivery hasn't happened — it now has.
- Added `EMAIL_PROVIDER`/`EMAIL_FROM_ADDRESS`/`SMS_PROVIDER` settings,
  mirroring the existing `AIRLINE_PROVIDER`/`PAYMENT_PROVIDER` mock/real
  split, both defaulting to `mock`.
- Wrote 31 new dependency-free tests
  (`tests/test_notifications_core.py`), all passing, and re-ran the full
  pinned suite (267/267, 8 skips, unchanged) to confirm nothing else
  broke.
- Fetched Resend's and Twilio's current API references live this
  session and built both real providers against them, not against
  training-data assumptions — same discipline T-3/T-4 applied to
  Stripe/Vapi.
- Found, and deliberately did not fix (out of scope), two pre-existing
  data-model gaps: `Booking.cancellation_deadline` is never populated
  anywhere in this codebase, and `Booking` does not persist which cabin
  class was booked.
- Found, and fixed as part of this session's own documentation pass, a
  pre-existing drift in several docs where the dependency-free test
  count/breakdown had gone stale (`docs/PROJECT_STATE.md`,
  `docs/PROJECT_ROADMAP.md`, `docs/PRODUCTION_CHECKLIST.md`, and
  `.github/workflows/t1-verify.yml`'s `EXPECTED = 223` — the workflow
  should have been updated to 236 after T-3 and never was).
- Updated all of the following documentation to reflect the above:
  `docs/TASK_BOARD.md`, `docs/PROJECT_STATE.md`,
  `docs/PROJECT_ROADMAP.md`, `docs/WORK_BREAKDOWN_STRUCTURE.md`,
  `docs/PAYMENTS.md`, `docs/ENVIRONMENT_VARIABLES.md`,
  `docs/PRODUCTION_CHECKLIST.md`, `docs/ARCHITECTURE.md`, `README.md`,
  `docs/MASTER_RULES.md` §7, `.github/workflows/t1-verify.yml`.

## 3. Files created

- `apps/api/app/core/notifications/__init__.py`
- `apps/api/app/core/notifications/content.py`
- `apps/api/app/services/sms_provider.py`
- `apps/api/app/services/notification_service.py`
- `apps/api/tests/test_notifications_core.py`
- `docs/handoffs/2026-09-09-t5-notifications.md` (this file)

## 4. Files modified

- `apps/api/app/services/email_provider.py` — extended (see §5)
- `apps/api/app/services/booking_service.py` — `notifier` param + a
  post-commit notification call in `create_booking`
- `apps/api/app/services/payment_service.py` — `notifier` param + a
  post-commit notification call in `create_payment_session`
- `apps/api/app/api/routes/bookings.py` — `create_booking` route
  constructs and passes a `NotificationService`
- `apps/api/app/api/routes/payments.py` — `create_payment_session` route
  does the same
- `apps/api/app/api/routes/vapi.py` — `_dispatch_create_booking` and
  `_dispatch_create_payment_session` do the same; the latter's returned
  string rewritten
- `apps/api/app/core/vapi/tool_schemas.py` — `create_payment_session`'s
  description rewritten
- `apps/api/app/core/config.py` — new settings + production validation
- `.env.example` — new env vars
- `docs/TASK_BOARD.md`, `docs/PROJECT_STATE.md`,
  `docs/PROJECT_ROADMAP.md`, `docs/WORK_BREAKDOWN_STRUCTURE.md`,
  `docs/PAYMENTS.md`, `docs/ENVIRONMENT_VARIABLES.md`,
  `docs/PRODUCTION_CHECKLIST.md`, `docs/ARCHITECTURE.md`, `README.md`,
  `docs/MASTER_RULES.md`, `.github/workflows/t1-verify.yml`

## 5. Architecture changes

**Content/orchestration split, new this session.**
`app/core/notifications/content.py` holds plain dataclasses
(`PassengerSummary`, `BaggageAllowance`, `BookingConfirmationData`,
`PaymentLinkData`, `NotificationContent`) and pure functions that turn
them into subject/text/HTML (or an SMS string) — no SQLAlchemy, no
FastAPI, no network import anywhere in that file. This mirrors
`app/providers/payments/base.py`'s own discipline, but it's a new
pattern in this project in one respect: it's the first time content
*text generation itself* (not just state-machine/provider logic) has
been pulled out to be dependency-free-testable. The reasoning: a
notification's TEXT is the actual product surface a real customer sees,
and the two things most likely to go wrong with it — leaking a passport
number, inventing a cancellation fee or baggage figure the system
doesn't actually know — are exactly the kind of mistake a test can catch
mechanically if the logic producing that text is isolated enough to run
in this sandbox at all.

**`NotificationService` composition, mirroring T-3's `CancellationService`
pattern — with one deliberate difference.** T-3 made
`CancellationService`'s `payment_provider` dependency required, because
a missing one there would be a money-correctness bug. T-5 made
`NotificationService`'s presence on `BookingService`/`PaymentService`
*optional* (`Optional[NotificationService] = None`), because a missing
one here just means "no confirmation sent" — identical to every session
before this one, not a new failure mode. This kept the blast radius
small: only the two call sites that actually create something needed
updating; three other `BookingService` constructions, three other
`PaymentService` constructions, and `CancellationService`'s internal one
are untouched.

**Why SMS only for a live voice call, not every payment link.** WBS-4.4's
own exit criterion is "a payment link can actually reach a caller who
can't access a computer mid-call" — that's specifically the voice
scenario. A web-created session's browser already has `checkout_url` on
screen. `also_sms=(call_id is not None)` encodes exactly that boundary;
email goes out for every session regardless of channel (an unsolicited
confirmation email is standard practice; an unsolicited SMS felt like a
different, more intrusive thing to add without being asked).

**Why the baggage lookup lives in `BookingService`, not
`NotificationService`.** `BookingService` already holds an
`AirlineProvider` reference; giving `NotificationService` its own would
have added a second, redundant provider dependency to a class whose job
is dispatch, not domain lookups. `BookingService.create_booking()` calls
`self.provider.get_baggage_rules(CabinClass.ECONOMY,
aircraft_type=booking.aircraft_type)` itself, catches `ProviderError`,
and passes either a real `BaggageAllowance` or `None` into
`NotificationService.send_booking_confirmation`.

**Why `CabinClass.ECONOMY` specifically.** `Booking` does not persist
which cabin class was actually purchased — confirmed by reading the
model and the create-booking request schema before writing any of this,
not assumed. `CabinClass.ECONOMY` is already this codebase's own
system-wide default for "cabin class unspecified" (used in
`search_flights`/`get_fare_quote`'s own signatures), so reusing it here
is a documented, consistent choice, not a new convention invented for
this task. It's an honest simplification, not a fabricated number — the
alternative (adding a `cabin_class` column to `Booking`) is a schema
change outside T-5's authorized scope and is recorded as a known gap
instead (§12/§15 below).

## 6. Database changes

None. No new columns, no new migration. `NotificationService` writes
`AuditLog` rows through the existing `record_audit_event` helper — no
schema change needed for that.

## 7. API changes

No new routes, no new request/response schemas. `POST /api/v1/bookings`
and `POST /api/v1/payments/sessions` (and the equivalent Vapi tool
dispatch functions) behave identically from the caller's point of view —
same request shape, same response shape, same status codes. The only
externally-observable difference is a side effect: a real email (and,
for a voice-originated payment session, SMS) now goes out when
`EMAIL_PROVIDER`/`SMS_PROVIDER` are set to `resend`/`twilio` — which
they are not by default.

## 8. Integration changes

Two new outbound integrations, both **written and cross-checked against
live provider documentation this session, never executed**:

- **Resend** — `POST https://api.resend.com/emails`, Bearer auth,
  `Idempotency-Key` header. Fetched from
  `resend.com/docs/api-reference/emails/send-email` and corroborated
  error-shape sources this session.
- **Twilio** — `POST
  https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages.json`,
  HTTP Basic auth, `I-Twilio-Idempotency-Token` header. Fetched from
  `twilio.com/docs/messaging/api/message-resource` and corroborated
  error-shape/idempotency sources this session.

Both use `httpx`, already a project dependency, lazily imported inside
the method that needs it — same reasoning `StripePaymentProvider`
lazy-imports `stripe`: selecting the `mock` provider (the default) must
never require the real package to even be importable.

## 9. Security changes

No new attack surface beyond what already existed. Two points worth
recording explicitly:

- **Passport data cannot reach a notification, structurally.**
  `PassengerSummary` (the only passenger-shaped object any content
  builder ever sees) has exactly three fields —
  `first_name`/`last_name`/`passenger_type` — and no passport-shaped
  field exists anywhere in `app/core/notifications/content.py`. This
  isn't a redaction step that could be forgotten; there's nothing to
  redact because the data was never passed in. Tested directly:
  `test_passenger_summary_has_no_passport_shaped_field` inspects
  `dataclasses.fields()` itself, and
  `test_no_content_ever_contains_the_word_passport` checks the
  generated text.
- **`NotificationService` is not a Vapi tool and cannot become one by
  accident.** It has no entry in `TOOL_AUTHORIZATION_MATRIX`, no JSON
  schema in `tool_schemas.py`, and is only ever constructed inside
  `BookingService`/`PaymentService`/two route files — never inside
  `app/api/routes/vapi.py`'s dispatch table directly for a
  caller-invoked action. This was a deliberate design constraint from
  MASTER_RULES §6, not an incidental result.

## 10. Tests executed — exact results

```
cd apps/api && python3 -m unittest tests.test_core_logic \
  tests.test_security_core tests.test_vapi_core tests.test_payments_core \
  tests.test_api_security tests.test_vapi_api tests.test_notifications_core -v
```

Result: **`OK`, 267 tests, 0 failures, 0 errors, `skipped=8`.** The 8
skips are unchanged from before this session (the same 6
`test_api_security.py` classes + 2 `test_vapi_api.py` classes, same
reason: `"FastAPI/SQLAlchemy stack not installed"`). 236 pre-existing +
31 new in `tests/test_notifications_core.py`, all 31 new tests passing.

Additionally, independently confirmed by direct execution (not
assumption):
- `python3 -c "from app.services.email_provider import ...; from
  app.services.sms_provider import ...; from
  app.core.notifications.content import ..."` — imports cleanly with
  neither `httpx` nor `sqlalchemy` installed in this sandbox.
- `python3 -c "from app.services.notification_service import
  NotificationService"` — correctly raises `ModuleNotFoundError: No
  module named 'sqlalchemy'`, same as every other `app/services/*.py`
  file, confirming it was NOT accidentally made dependency-free (it
  shouldn't be — it needs a real `Session`).
- Every one of the 13 Python files touched this session individually
  passes `python3 -c "import ast; ast.parse(open(path).read())"`.
- The edited `.github/workflows/t1-verify.yml` parses as valid YAML
  (`yaml.safe_load`).

## 11. Runtime verification status

Same three-tier split T-3/T-4 used:

- **Verified locally, this session:** everything in §10 above.
- **Written, reviewed, cross-checked against live provider docs fetched
  this session, NOT executed:** `ResendEmailProvider`,
  `TwilioSmsProvider`, and every code path inside
  `NotificationService`/the `BookingService`/`PaymentService` changes/the
  three edited routes that needs SQLAlchemy or FastAPI — neither
  installable here (`pip install httpx` returns `403`, re-confirmed this
  session, same as every prior one since Phase 4).
- **Requires external verification, BLOCKED:** a real send against
  Resend, a real send against Twilio, and an end-to-end
  `create_booking`/`create_payment_session` run with
  `EMAIL_PROVIDER=resend`/`SMS_PROVIDER=twilio` against a real Postgres
  database (needs T-1's still-blocked dependency install too).

## 12. Known limitations (this session)

- Payment-link SMS is sent only when the session was created during a
  live voice call (`call_id is not None`) — a web-created session never
  gets a text, only an email. Deliberate scope boundary, see §5.
- Booking-confirmation is email-only — no SMS variant was built for it
  (not asked for in WBS-4.3's spec-§44 content list, and that content
  doesn't fit an SMS segment anyway).
- The booking-confirmation email's cancellation-terms line is always the
  honest generic sentence, never a specific date, because
  `Booking.cancellation_deadline` is never populated by anything in this
  codebase — a pre-existing gap, found this session, not fixed (see
  §15).
- The baggage-allowance line defaults to `CabinClass.ECONOMY` regardless
  of the fare actually purchased, because `Booking` doesn't persist
  cabin class — same pre-existing-gap situation, see §15.
- No SMTP fallback was built for email — Resend only, per §5's decision
  log entry in `docs/TASK_BOARD.md`'s T-5 section.
- `NotificationService`'s own audit-write (`_audit()`) can itself fail
  (e.g. if the DB connection is bad) — that failure is caught and
  swallowed too (`except Exception: self.db.rollback()`), meaning it's
  theoretically possible for a real send to succeed or fail with zero
  audit trail of it if the database itself is unavailable at that exact
  moment. Judged an acceptable, deliberately narrow edge case rather
  than something worth a retry queue or a dead-letter mechanism, which
  would be real scope creep beyond what T-5 authorized.

## 13. Blocked items

Identical root cause across all of them: no network egress in this
sandbox.

- A real Resend API call (any of `ResendEmailProvider`'s methods).
- A real Twilio API call (`TwilioSmsProvider.send_payment_link`).
- `pip install -r requirements.txt` (needed to even import `httpx` for
  real, on top of `fastapi`/`sqlalchemy`/`stripe`, all already blocked
  since Phase 4).
- Everything already blocked from T-1/T-3/T-4 remains blocked, unchanged
  by this session.

## 14. Deferred items (explicitly out of this session's scope)

- SMTP as a second email provider (WBS-4.1 offered either Resend or
  SMTP; Resend was chosen — see §5).
- Adding `cabin_class` to `Booking` to get an exact per-fare baggage
  figure instead of the `CabinClass.ECONOMY` default.
- Populating `Booking.cancellation_deadline` anywhere in the booking
  flow.
- Sending a payment-link SMS for web-created sessions too.
- Any retry/dead-letter mechanism for a failed notification send (see
  §12's last bullet).
- Admin dashboard (Phase 9) — untouched.

## 15. Pre-existing issues discovered but NOT fixed (out of authorized scope)

- **`Booking.cancellation_deadline` is a nullable column nothing in this
  codebase has ever populated.** Confirmed by `grep -rn
  "cancellation_deadline"` across `apps/api/app` before writing any
  content-builder logic — it's declared in the model, the migration, and
  `BookingOut`, and read back out in `bookings.py`'s response mapping,
  but never *written* anywhere in `create_booking`/`modify_booking`.
  Fixing this (deciding the actual policy for when/how a deadline gets
  set) is a `BookingService`/cancellation-policy design decision outside
  T-5's scope — recorded here and in `docs/PROJECT_ROADMAP.md` §9 rather
  than silently worked around or silently left undocumented.
- **`Booking` does not persist which `CabinClass` was booked.** Same
  situation — confirmed by reading the model and
  `BookingCreateRequest`/`BookingModifyRequest` schemas before writing
  the baggage-lookup code, not assumed. T-5's own baggage lookup works
  around this honestly (documented `CabinClass.ECONOMY` default,
  disclosed in three places: `content.py`'s docstring,
  `notification_service.py`'s docstring, and here) rather than either
  fabricating a number or silently pretending the gap doesn't exist.
- **`.github/workflows/t1-verify.yml`'s `EXPECTED` value was stale at
  223, not 236, even though T-3 had already raised the real baseline to
  236 the day before this session started.** This means the workflow's
  own baseline-verification step would have hard-failed CI (asserting
  "223" against an actual 236) had it ever been run in a networked
  environment between T-3 and this session — it never was, since T-1
  remains blocked, so this never actually broke anything observable, but
  it was a real, live bug in the CI gate. Fixed as part of this session
  (now 267) rather than left for the next one, since it's the exact kind
  of thing this session was already touching anyway.

## 16. Remaining work within the project

Unchanged from T-4's handoff, plus T-5's own additions:

- T-1: install the real dependency stack and run every FastAPI/
  SQLAlchemy-level test for real, in a networked environment.
- T-4: run `scripts/setup_vapi.py --apply` against a real Vapi account;
  place a real inbound call; verify `transferCall`.
- **T-5 (new):** set real `RESEND_API_KEY`/`TWILIO_*` credentials in a
  networked environment, flip `EMAIL_PROVIDER=resend`/
  `SMS_PROVIDER=twilio`, and confirm a real booking/payment session
  actually triggers a real, correctly-formatted email/SMS.
- Phase 9 (admin dashboard) — not started.
- Phase 10 (Playwright E2E, voice conversation test suite) — not
  started.
- The Phase 6/7 numbering decision (T-2 in `docs/TASK_BOARD.md`) — still
  an open, unauthorized decision, not a coding task.

## 17. Recommended next step

Same recommendation as T-3's and T-4's handoffs, now with three tasks'
worth of accumulated unexecuted FastAPI/SQLAlchemy code riding on it: get
this repository into an environment with real network access and run
`pip install -r requirements.txt` followed by the full test command in
§10, then `docker compose up --build`. This is the single highest-
leverage action available — it converts T-3's refund logic, T-4's
telephony setup script's real-account behavior, and T-5's entire
service-layer/route/notification-provider surface from "written,
reviewed" to either "confirmed working" or "found a real bug," all at
once, the same way it would have for every phase before these three.

## 18. Anything the next session must know

- **This session was explicitly authorized by the project owner's direct
  instruction** ("Execute and authorize T-5") — `docs/TASK_BOARD.md`'s
  T-5 entry records this the same way T-4's entry recorded its own
  authorization. If a future session's context doesn't include this
  conversation, `docs/TASK_BOARD.md` is the record of record, not this
  handoff's framing of it.
- **`notifier` is optional on `BookingService`/`PaymentService` on
  purpose** — don't "fix" it to be required without re-reading §5's
  reasoning first; making it required would force updating
  `CancellationService`'s internal `PaymentService` construction and
  every read-only route's `BookingService`/`PaymentService` construction
  for no behavioral benefit.
- **Two data-model gaps are now documented in three places each**
  (`docs/PROJECT_ROADMAP.md` §9, `docs/TASK_BOARD.md`'s T-5 entry, and
  this handoff) — if a future session decides to fix either one
  (`cancellation_deadline` population or persisting `cabin_class`), it
  should read all three before starting, since between them they record
  not just "what's missing" but "where the boundary of what depends on
  it currently sits" (the notification content builders, specifically).
- **Do not assume a real email/SMS has ever been sent by this system.**
  Every test in `tests/test_notifications_core.py` exercises
  `MockEmailProvider`/`MockSmsProvider` or the pure content builders —
  zero HTTP calls have ever left this sandbox for either provider.
