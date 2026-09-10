# Charter123 — Task Board

**This file controls what may be implemented. Being described in
`docs/PROJECT_ROADMAP.md` or `docs/WORK_BREAKDOWN_STRUCTURE.md` does
NOT mean a task is authorized — check here first, every session.**

Format per task: Status, Scope (exactly what may be touched), Explicitly
NOT in scope, Depends on, Authorized by / date.

Status values: `AUTHORIZED` (may be started now) · `PROPOSED` (WBS has a
plan, owner hasn't authorized it yet) · `DONE` (completed, see the linked
handoff) · `BLOCKED` (authorized in principle, blocked on an external
dependency).

---

## Currently authorized

### T-1 — Install & execute the FastAPI/SQLAlchemy test layer for real
- **Status:** BLOCKED (authorized in principle, blocked on an external
  dependency — see "Attempt log" below).
- **Scope:** In a networked environment, `pip install -r
  apps/api/requirements.txt`, then run `tests/test_api_security.py` and
  `tests/test_vapi_api.py` for real (currently skip cleanly everywhere
  this project has been built). Fix whatever real bugs surface — this is
  exactly the kind of execution that has caught every real bug so far
  (see `PROJECT_HANDOFF_PHASE_4.md`/`_5.md` §12 for the bug lists).
- **NOT in scope:** any new feature. This is pure verification.
- **Depends on:** network access to a package index.
- **Authorized by:** project owner, 2026-09-07 (this session).
- **Attempt log (2026-09-07, same session as authorization):**
  - `pip install --break-system-packages -r apps/api/requirements.txt`
    → fails: `ERROR: Could not find a version that satisfies the
    requirement fastapi<0.116,>=0.115 (from versions: none)`. This
    sandbox's egress proxy returns `403` with header `x-deny-reason:
    host_not_allowed` for `pypi.org`.
  - No `docker` binary present in this sandbox (`which docker` → not
    found) — `docker compose up` (WBS-1.4) is equally unreachable.
  - No vendored wheels, no pip cache, no alternate `--index-url`
    configured anywhere in the repo or sandbox pip config that would
    permit an offline install.
  - **This is the same blocker already on record** in
    `docs/PROJECT_ROADMAP.md` §8/§9 ("no networked build/test
    environment has ever been available") — re-confirmed, not a new
    finding.
  - What **could** be verified without network: the full dependency-free
    suite was re-run independently this session —
    `cd apps/api && python3 -m unittest tests.test_core_logic
    tests.test_security_core tests.test_vapi_core tests.test_payments_core
    tests.test_api_security tests.test_vapi_api -v` → **223 tests, OK,
    skipped=8**. The 8 skips are exactly the 6 `test_api_security.py`
    classes + 2 `test_vapi_api.py` classes, each with reason
    `"FastAPI/SQLAlchemy stack not installed: No module named
    'fastapi'"` — confirms the skip is precisely the documented network
    blocker, not a different or newly-introduced failure. No code was
    changed; nothing was "fixed" because nothing beyond the known
    blocker was reachable to test.
- **Attempt log (2026-09-07, second attempt, same session, exhaustive
  environment search):** re-confirmed BLOCKED after explicitly trying
  every fallback a networked/alternate environment might offer, not just
  the default `pip install`:
  - **Inspected dependency declarations first:** the only dependency
    file in the repo is `apps/api/requirements.txt` (no `pyproject.toml`,
    no lock file, no separate `requirements-dev.txt` — dev/test deps
    are the same file's trailing `pytest`/`pytest-cov` lines). No
    `.python-version` or pinned interpreter version anywhere in the
    repo. Versions declared are internally consistent (`fastapi>=0.115`,
    `pydantic>=2.9`, `SQLAlchemy>=2.0.35`, `stripe>=11.1`, etc.) — the
    blocker is not a project-side dependency problem.
  - **Python version:** 3.12.3 (`/usr/bin/python3.12`) — satisfies every
    declared constraint; not the blocker.
  - **Existing venv:** none found anywhere under the repo or home
    directory.
  - **New venv:** would still need network to populate with the
    declared packages — not attempted as pointless without network.
  - **Docker:** `docker` binary not present in this sandbox at all.
  - **Alternate interpreters:** only one Python install on this machine
    (3.12.3); no pyenv/conda/other version.
  - **PyPI:** `pip install --break-system-packages -r
    apps/api/requirements.txt` → `ERROR: Could not find a version that
    satisfies the requirement fastapi<0.116,>=0.115 (from versions:
    none)`. `pip download sqlalchemy` → same "from versions: none"
    result.
  - **Network egress, tested directly against multiple hosts** (not
    just PyPI, to rule out a PyPI-specific block): `curl -I
    https://pypi.org` → `403`, header `x-deny-reason: host_not_allowed`.
    Same `403` for `https://files.pythonhosted.org` and
    `https://github.com`.
  - **OS package manager as a fallback path:** `apt-get update` also
    fails — `archive.ubuntu.com`, `security.ubuntu.com`, and
    `deb.nodesource.com` all return `403 Forbidden` at the network
    layer, same pattern as PyPI. This confirms the block is a blanket
    egress restriction on this sandbox, not something specific to PyPI
    that a different index or mirror could route around.
  - **No override available:** no proxy env var, no alternate
    `--index-url`, no cached wheels, no pip cache — nothing to point at
    instead.
  - **Conclusion:** this is a platform-level restriction on the tool
    Claude is given in this chat session (network disabled for its
    command-execution tool), not something resolvable by searching
    harder inside the same session. It requires either the project
    owner running this on their own machine/CI with real network access
    (as already recommended), or enabling network access for Claude's
    tool in this product's settings, if that option exists here.
- **Workflow hardened (2026-09-07, fourth attempt — still NOT run):**
  validated `.github/workflows/t1-verify.yml` line-by-line against the
  real repo (not assumed correct) and fixed two real defects found by
  that validation, both confirmed against external sources, not
  assumption:
  1. **Silent-pass bug:** the test-run step piped output through `tee`
     without `shell: bash` explicitly set. GitHub Actions' default
     (unspecified) shell does NOT apply `pipefail` (confirmed against
     `actions/runner-images#4459`, a reported case of exactly this
     masking a real test failure, and GitHub's own corrected docs) — so
     `cmd | tee file` would have reported `tee`'s exit code, not the
     test run's, meaning a real test failure could have shown green.
     Fixed with `defaults: run: shell: bash` at the workflow level, and
     the test step now redirects to a file instead of piping, with a
     separate step deterministically parsing the captured output
     (exact 223-test count, zero skips of any kind — not just the one
     previously-known skip string —, no FAILED/ERROR, a clean `OK`
     line). Validated by actually running this parser against four
     synthetic unittest outputs (clean pass / still-skipping /
     wrong-count / real-failure) before trusting it.
  2. **Fragile version check:** `stripe.__version__` was not confirmed
     to exist on the pinned `stripe>=11.1,<12.0` — stripe-python's own
     changelog (PR #1645) describes moving to lazy `__getattr__`-based
     attribute resolution, so a bare `__version__` access isn't
     guaranteed stable. Replaced with `importlib.metadata.version()` for
     all four packages, which reads installed-distribution metadata
     regardless of what a package internally exposes.
  Also explicitly checked and confirmed correct (no changes needed):
  readiness-before-migration ordering (`/ready` only does `SELECT 1` +
  Redis ping, confirmed by reading `health.py` — safe pre-migration);
  `test_api_security.py`/`test_vapi_api.py` use `unittest.TestCase` with
  a `setUp()`-level `SkipTest` (confirmed by reading the files), so
  `python -m unittest` genuinely exercises them once deps install,
  regardless of their own docstrings suggesting `pytest`; Docker Compose
  V2 is preinstalled on `ubuntu-latest` (confirmed against
  `actions/runner-images`' own Ubuntu 24.04 readme); postgres/redis
  service names and ports match `docker-compose.yml` exactly; `alembic`'s
  `env.py` overrides `alembic.ini`'s placeholder URL from
  `get_settings().database_url` (confirmed by reading `env.py`), so
  migrations target the right database; `python -m app.db.seed` matches
  the script's own documented invocation.
  **Still NOT run** — no GitHub Actions execution has occurred. Status
  remains **BLOCKED**.
- **Tooling prepared (2026-09-07, third attempt):** since Claude's own
  sandbox has no network/Docker and no GitHub connector is available to
  it (checked — no GitHub or CI connector is connected in this
  workspace), `.github/workflows/t1-verify.yml` was written and added to
  this repo, grounded in the actual `docker-compose.yml`, `Dockerfile`s,
  `alembic.ini`, and `app/db/seed.py` — not guessed. It has NOT been run.
  Two jobs: (1) real `pip install` + the full test suite, failing the
  build if `test_api_security.py`/`test_vapi_api.py` still skip; (2)
  `docker compose up`, `alembic upgrade head`, `python -m app.db.seed`,
  and a live `/api/v1/health/ready` check. Status stays **BLOCKED** here
  until the project owner pushes this file and runs it on GitHub, and
  the actual pass/fail result is reported back.
- **Remaining to close this task:** run in an environment with actual
  network access to PyPI (outside this sandbox), then complete WBS-1.2
  through WBS-1.7 (`docker compose up`, `alembic upgrade head`,
  `python -m app.db.seed`, and update `docs/PROJECT_STATE.md`'s
  "Verified" columns for whatever that closes).

### T-3 — Phase 7 remainder: `refund_payment`
- **Status:** AUTHORIZED — implementation done this session; execution
  status is split (see below), same T-1 sandbox constraint as every
  other `apps/api/app/services/*.py` / `app/api/routes/*.py` file.
- **Scope:** Implement the reserved, `STAFF_OR_ADMIN_ONLY` `refund_payment`
  route against `PaymentProvider` (staff/finance-only REST endpoint —
  confirmed NOT a Vapi tool, since `STAFF_OR_ADMIN_ONLY` always denies a
  `VAPI_AGENT` actor and `test_authorization_entries_without_a_schema_
  are_exactly_staff_only` already pins this), and fix `CancellationService.
  cancel()`'s local-only `REFUNDED` flip (see `docs/PAYMENTS.md` §9) to
  actually call it when a paid booking is cancelled.
- **NOT in scope:** payment-link delivery (T-5), telephony (T-4), a
  refund-status-change webhook subscription (Stripe's `refund.updated`/
  `charge.refunded` events — this milestone only trusts the synchronous
  response from `POST /v1/refunds`; a refund that comes back `pending`/
  `requires_action` is recorded as such, not resolved later — see
  `docs/PAYMENTS.md` "Known limitations," new entry).
- **Depends on:** T-1 recommended first; a Stripe test-mode account for
  end-to-end verification. Neither available in this sandbox — see
  Testing status below.
- **Authorized by:** project owner, 2026-09-08 (this session).
- **What was built:**
  - `PaymentProvider.refund_payment()` (new abstract method) +
    `RefundResult`/`RefundStatus` + `PaymentRefundError`, implemented in
    both `MockPaymentProvider` (deterministic, dependency-free) and
    `StripePaymentProvider` (real `stripe.Refund.create`, cross-checked
    against Stripe's current Refunds API reference — fetched this
    session, not assumed from training data).
  - `Payment` model gained `provider_refund_id`/`refunded_amount`/
    `refund_status`/`refunded_at`/`refund_reason` (migration `0005`).
    Deliberately did NOT touch `app/core/payments/state_machine.py`'s
    session-status vocabulary (`Payment.status` never becomes
    `"REFUNDED"` — it stays `SUCCEEDED` forever once paid) — the refund
    lifecycle is orthogonal, tracked in the new columns only. This keeps
    `test_booking_payment_status_mapping_never_produces_refunded` (and
    every other `StateMachineTests` assertion) true without modification;
    `Booking.payment_status` (a plain string field, not state-machine-
    governed) is what still flips to the pre-existing `"REFUNDED"` value.
  - `PaymentService.apply_refund_outcome()` (shared, non-committing —
    mutates `Payment`/`Booking` fields + writes the audit row only) and
    `PaymentService.refund_payment()` (staff-facing, owns its own
    commit/rollback + idempotency-store transaction, mirrors
    `create_payment_session` exactly). A partial refund only flips
    `Booking.payment_status` to `"REFUNDED"` once the FULL remaining
    amount has been returned; a goodwill partial refund on an active
    booking leaves it `"PAID"`.
  - `CancellationService.cancel()` now takes a 4th constructor arg
    (`payment_provider: PaymentProvider`) and, for a PAID booking, calls
    the provider directly (via the same `apply_refund_outcome` helper,
    but WITHOUT calling `PaymentService.refund_payment()`'s own commit/
    rollback — both must not nest on the same `Session`, see that
    module's new comment) using the airline's `CancellationResult.
    refundable_amount` (net of `cancellation_fee`) — not `Payment.amount`
    outright. Always sets `Booking.payment_status = "REFUNDED"` on a
    successful paid cancellation (full OR fee-adjusted — matches the
    pre-existing intent this "known limitation" comment already
    described, now backed by a real provider call). If the provider call
    itself fails, the airline cancellation is NOT rolled back (it already
    happened and can't be undone locally) — `Booking.payment_status`
    stays `"PAID"` (never falsely `"REFUNDED"`) and an audit event
    (`payment.refund_failed_during_cancellation`) records it; the new
    staff `refund_payment` route is the manual recovery path for exactly
    this case.
  - `POST /api/v1/payments/refunds` (`app/api/routes/payments.py`) —
    `require_payment_access(..., required_permission=Permission.
    PAYMENTS_REFUND.value)`, identical gate shape to the existing two
    payment routes; `RefundCreateRequest` requires an explicit
    `confirmed: True` (mirrors `customer_confirmed` on the other payment/
    booking mutations — MASTER_RULES §3's explicit-confirmation pattern,
    extended here since a staff-initiated refund is exactly the kind of
    "mutation with real consequences" that pattern exists for, even
    though `refund_payment` isn't one of §3's literally-enumerated Vapi
    tool names).
  - All 4 `CancellationService(...)` call sites updated
    (`app/api/routes/bookings.py` x2, `app/api/routes/vapi.py` x2) to
    pass `get_payment_provider()`.
  - `_PAYMENT_PROVIDER_ERROR_HTTP_STATUS["PAYMENT_REFUND_FAILED"] = 502`
    added to `app/core/exceptions.py`.
- **Testing status (§7 — stated exactly, not rounded up):**
  - **Verified locally:** the new `state_machine.py`-adjacent and
    provider-layer logic — 12 new tests in `tests/test_payments_core.py`
    (`RefundResult`/`RefundStatus`/`PaymentRefundError` shape,
    `MockPaymentProvider.refund_payment` full/partial/idempotent-replay/
    over-refund/unpaid-session/unknown-payment-intent cases). Full
    dependency-free suite re-run after the change — see the handoff for
    the exact command and count.
  - **Written, reviewed, not executed:** `app/models/payment.py`'s new
    columns, migration `0005`, `PaymentService.apply_refund_outcome`/
    `refund_payment`, `CancellationService.cancel()`'s new branch, the
    `POST /refunds` route, and `StripePaymentProvider.refund_payment` —
    every one of these needs SQLAlchemy/FastAPI (`CancellationService`/
    `PaymentService`/routes) or `stripe` (the Stripe provider), none of
    which import in this sandbox (confirmed again this session:
    `python3 -c "import fastapi"` / `sqlalchemy` / `stripe` all raise
    `ModuleNotFoundError`). This is the identical, already-documented T-1
    constraint — nothing new.
  - **Requires external verification:** `StripePaymentProvider.
    refund_payment` against a real Stripe test-mode account (a live
    PaymentIntent, a real partial refund, confirming the `succeeded` vs
    `pending` status split actually behaves as the Refunds API reference
    describes) — cannot be exercised until T-1's environment exists.

### T-4 — Phase 6 remainder: telephony
- **Status:** AUTHORIZED — `scripts/setup_vapi.py` (WBS-2.1) written and
  its dependency-free logic executed this session; WBS-2.2 through 2.5 (a
  real number, a real inbound call, live `transferCall` verification)
  remain **BLOCKED** on the same external dependency the scope always
  named — a live Vapi account — compounded by this sandbox's standing
  no-network-egress constraint (see T-1's Attempt log; re-confirmed
  independently this session, not assumed from T-1's record).
- **Scope:** `scripts/setup_vapi.py` (spec §51: create/update tools,
  create/update assistant, configure webhook, attach a phone number);
  connect a real number; one real inbound test call; configure the
  native `transferCall` tool per `docs/VAPI.md`'s instructions.
- **NOT in scope:** any change to existing tool logic — this is
  configuration/scripting only, on top of what Phase 5 already built.
- **Depends on:** a live Vapi account.
- **Authorized by:** project owner, 2026-09-09 (this session — moved
  from Proposed to Authorized on explicit instruction. WBS-2's own
  "Dependencies: WBS-1 recommended first" note was not satisfied — T-1 is
  still BLOCKED — flagged here rather than silently ignored, but not
  treated as a hard blocker for authorization, since T-4's own listed
  dependency is a live Vapi account, not T-1, and the owner authorized
  proceeding anyway.)
- **What was built:**
  - `scripts/setup_vapi.py` (WBS-2.1) — idempotent create-or-update for
    all 21 `app.core.vapi.tool_schemas.VAPI_TOOL_SCHEMAS` function tools,
    the native `transferCall` tool (only if a destination number is
    supplied), the Assistant (`model.toolIds` + a system prompt read
    directly from `docs/VAPI.md`'s own "Suggested system prompt" section
    at runtime, so the two can never silently drift), and phone-number
    attachment. Every Vapi API shape used (`POST`/`GET`/`PATCH /tool`,
    `POST`/`PATCH /assistant`, `PATCH /phone-number/{id}`, the
    `server.secret`/`server.credentialId` authentication split) was
    fetched from docs.vapi.ai this session — not assumed from training
    data, which predates Vapi's current Custom Credentials system.
  - **New finding, cross-checked, does not contradict existing code:**
    Vapi's current documentation describes a dashboard-managed "Custom
    Credentials" system as the primary webhook-auth mechanism now, with
    the older inline `server.secret` field kept working under an
    explicit "Migration from Inline Authentication" compatibility note.
    This matches — does not contradict — what
    `app/core/security/vapi_webhook_auth.py`'s own docstring already
    independently recorded (dated "September 2026"). No public API
    endpoint for creating a Custom Credential was found anywhere in
    Vapi's API reference resource list — every source describing
    credential creation describes the dashboard only. `setup_vapi.py`
    therefore defaults to `VAPI_WEBHOOK_SECRET` (the same variable the
    running app already reads) and accepts an optional
    `VAPI_WEBHOOK_CREDENTIAL_ID` for anyone who creates a Custom
    Credential by hand in the dashboard and wants the script to
    reference it instead.
  - `scripts/test_setup_vapi.py` — 24 dependency-free unit tests covering
    every pure function: payload builders for all three resource types,
    the system-prompt loader (including its two error paths), and
    create-vs-update upsert planning — including the rule that the
    script refuses to guess which `transferCall` tool to update if more
    than one already exists on the account, rather than picking one.
  - The networked half (`VapiClient`, and everything inside `main()`'s
    `--apply` branch) is Written, reviewed, and cross-checked against the
    live docs above — NOT executed. `httpx` is imported lazily inside
    `VapiClient.__init__` specifically so the dependency-free half stays
    importable and testable without it, and so a plain `--dry-run`
    invocation needs no dependencies beyond the Python standard library
    at all.
- **Testing status (§7 — stated exactly, not rounded up):**
  - **Verified locally, this session:** `cd scripts && python3 -m
    unittest test_setup_vapi -v` → `OK`, 24 tests, 0 failures, 0 errors,
    0 skips. Also ran the CLI itself directly end to end (`python3
    scripts/setup_vapi.py --model-provider openai --model-name gpt-4o
    --transfer-number "+15551234567"`, no `--apply`) — printed the
    correct 21-tool + `transferCall` plan and a well-formed assistant
    payload containing the real system prompt loaded live from
    `docs/VAPI.md`, confirming the zero-dependency dry-run path works
    end to end, not just at the unit-test level.
  - One real bug was caught by execution, not review: the first draft
    imported `app.core.config.get_settings()`, a pydantic model —
    pydantic isn't importable in this sandbox either, so that single
    import broke even the dependency-free dry-run path before any test
    ran. Replaced with direct `os.environ` reads of the same variable
    names `Settings` defines; re-ran the full test file afterward to
    confirm the fix (24/24 passing after the change; a hard import
    failure before it — not silently patched over).
  - **Written, reviewed, not executed:** `VapiClient` and every
    `--apply`-path call inside `main()` — needs `httpx` (not installed
    here, confirmed again this session: `ModuleNotFoundError: No module
    named 'httpx'`), network egress to `api.vapi.ai` (confirmed blocked
    again this session: `403`, header `x-deny-reason: host_not_allowed`,
    same as every other outbound host T-1 already tested), and a real
    `VAPI_API_KEY` — none of which exist in this sandbox.
  - **Requires external verification / BLOCKED, same class as T-1:**
    - Running `setup_vapi.py --apply` against a real Vapi account for
      the first time (nothing in this script has ever executed a real
      Vapi API call).
    - WBS-2.2: connecting/attaching a real phone number.
    - WBS-2.4: placing one real inbound test call.
    - WBS-2.5: confirming the native `transferCall` handoff actually
      transfers a live call — not just that the tool object was created.
    - Deciding whether to move the webhook secret to a dashboard-created
      Custom Credential (`VAPI_WEBHOOK_CREDENTIAL_ID`) instead of the
      legacy inline `secret` field — a product/ops choice, not something
      this script or session can make.
- **Remaining to close this task:** a project owner (or CI) with real
  network access and a live Vapi account needs to: set `VAPI_API_KEY` /
  `VAPI_SERVER_URL` / `VAPI_WEBHOOK_SECRET` (or
  `VAPI_WEBHOOK_CREDENTIAL_ID`) in the environment; run `setup_vapi.py
  --apply` once; save the printed `VAPI_ASSISTANT_ID` back into `.env`
  (re-running `--apply` without it creates a second assistant instead of
  updating the first — the script prints this warning inline); attach or
  buy a real number, set `VAPI_PHONE_NUMBER_ID`, and re-run `--apply` to
  attach it; then place one real inbound call and confirm both an
  ordinary tool call and a transfer-to-human handoff actually work.

---

### T-5 — Phase 8: notifications
- **Status:** AUTHORIZED — moved from Proposed to Authorized on the
  project owner's explicit instruction, 2026-09-09 (this session), same
  mechanism T-4 used. Implementation done this session; live Resend/
  Twilio execution against real accounts is **BLOCKED**, same class as
  T-1/T-4 — this sandbox has no network egress (re-confirmed this
  session: `httpx` is not installed here either, so the question of
  reaching `api.resend.com`/`api.twilio.com` is moot regardless) and no
  real `RESEND_API_KEY`/`TWILIO_*` credentials exist in it.
- **Scope:** A real email provider (Resend) and a real SMS provider
  (Twilio), wired to booking-confirmation and payment-link delivery.
  Replaces `MockEmailProvider` with a real implementation behind the
  same interface; designs a new, sibling `SmsProvider` interface for SMS
  (none existed before this task) — do not change either interface's
  shape beyond what this task's own two new email methods and one new
  SMS method require.
- **NOT in scope:** admin dashboard (T-6); SMTP as a second email
  provider (the original WBS-4.1 wording said "Resend or SMTP" — Resend
  was chosen, SMTP was not built; see "Decisions/deviations" below);
  adding `cabin_class` to the `Booking` model to get an exact per-fare
  baggage figure (see "Known gap this task did not fix," below — an
  honest simplification instead, not scope creep into a schema change).
- **Depends on:** provider credentials (still true, per the original
  Proposed-section wording) — and, as of this session, also real network
  egress, which no sandbox this project has run in has ever had.
- **Authorized by:** project owner, 2026-09-09 (this session, explicit
  instruction to "Execute and authorize T-5").
- **What was built:**
  - `app/core/notifications/content.py` (NEW) — dependency-free content
    builders for both notification types. Stdlib-only on purpose (no
    SQLAlchemy/FastAPI import) so the actually risky part of this
    feature — what text goes out to a real customer — gets real,
    executed test coverage in this sandbox, the same way
    `MockPaymentProvider`'s refund math did in T-3. Two structural
    guarantees enforced here, not as a runtime check: (1) `PassengerSummary`
    has no passport-shaped field at all, so a booking-confirmation email
    cannot leak one; (2) `cancellation_deadline`/`baggage` are both
    `Optional` and the builders emit an honest generic sentence, never a
    guessed number, when either is unavailable (§1: "If the backend
    doesn't have it, say so honestly").
  - `app/services/email_provider.py` (EXTENDED) — `EmailProvider`'s
    original two methods (`send_password_reset`/`send_email_verification`,
    unchanged) plus two new ones (`send_booking_confirmation`/
    `send_payment_link`); `MockEmailProvider` extended to match;
    `EmailDeliveryError` (code/message/retryable) added; new
    `ResendEmailProvider` — real HTTP calls to `POST
    https://api.resend.com/emails` over lazily-imported `httpx`, using
    the `Idempotency-Key` header the same way `StripePaymentProvider`
    already forwards idempotency to Stripe. Resend's request/response/
    error shapes were fetched from Resend's own current API reference
    this session (`resend.com/docs/api-reference/emails/send-email`),
    not assumed from training data.
  - `app/services/sms_provider.py` (NEW) — `SmsProvider` Protocol (one
    method, `send_payment_link` — see "NOT in scope" above for why
    booking confirmation stays email-only); `MockSmsProvider`;
    `SmsDeliveryError`; `TwilioSmsProvider` — real HTTP calls to `POST
    .../Messages.json` over lazily-imported `httpx`, HTTP Basic Auth,
    the `I-Twilio-Idempotency-Token` header. Twilio's request/response/
    error shapes were fetched from Twilio's own current API reference
    this session (`twilio.com/docs/messaging/api/message-resource`), not
    assumed from training data.
  - `app/services/notification_service.py` (NEW) — `NotificationService`,
    the one place notification-dispatch logic lives (mirrors
    `PaymentService`'s own framing of itself). Converts ORM
    `Booking`/`Payment`/`BookingPassenger` objects into
    `content.py`'s plain dataclasses, dispatches to whichever
    email/SMS provider it was constructed with, and audits the outcome
    either way (`notification.{booking_confirmation,payment_link}_{sent,failed}`).
    Every public method catches its own provider's error type and NEVER
    re-raises — this is a SYSTEM-triggered side effect, never a step the
    booking/payment mutation that already succeeded depends on, and
    never a Vapi tool (MASTER_RULES.md §6 forbids exactly that).
  - `app/services/booking_service.py` / `app/services/payment_service.py`
    (EXTENDED) — both gained an `notifier: Optional[NotificationService]
    = None` constructor parameter, deliberately optional/defaulted so
    only the two call sites that actually create something (`create_
    booking`, `create_payment_session`) needed updating; the other
    `BookingService`/`PaymentService` construction sites in
    `bookings.py`/`payments.py`/`vapi.py`, and `CancellationService`'s
    internally-composed `PaymentService`, are UNCHANGED (`notifier`
    simply stays `None` there — the exact pre-T-5 behavior, not an
    error). `create_booking()` additionally looks up baggage via
    `self.provider.get_baggage_rules(CabinClass.ECONOMY,
    aircraft_type=...)` — `CabinClass.ECONOMY` because `Booking` does
    not persist which cabin class was actually booked (see "Known gap
    this task did not fix," below); on any `ProviderError` the baggage
    line is honestly omitted, never guessed.
  - `app/api/routes/bookings.py`, `app/api/routes/payments.py`,
    `app/api/routes/vapi.py` (EXTENDED) — the two creating routes/
    dispatch functions (`create_booking` x2, `create_payment_session`
    x2) now construct a `NotificationService` and pass it through.
    `PaymentService.create_payment_session`'s `also_sms` flag is
    `call_id is not None` — email always, SMS additionally only for a
    live voice call, which is the exact scenario `docs/PAYMENTS.md` §8
    documented as broken ("a phone caller who needs the link delivered
    has no path to receive it today except a human transfer").
  - `app/core/vapi/tool_schemas.py` — `create_payment_session`'s
    description rewritten: it previously instructed the assistant to
    say a link exists but explicitly NOT say it had been sent; it now
    says delivery is automatic and best-effort, matching the new
    reality. `vapi.py`'s `_dispatch_create_payment_session` return
    string updated the same way. No test asserted the old wording
    verbatim (checked before editing) — none needed updating as a
    result.
  - `app/core/config.py` / `.env.example` — `EMAIL_PROVIDER` (mock |
    resend) / `EMAIL_FROM_ADDRESS`, `SMS_PROVIDER` (mock | twilio),
    mirroring `AIRLINE_PROVIDER`/`PAYMENT_PROVIDER`'s exact mock/real
    split; `validate_for_production()` extended to require
    `RESEND_API_KEY`+`EMAIL_FROM_ADDRESS` when `EMAIL_PROVIDER=resend`
    and all three `TWILIO_*` values when `SMS_PROVIDER=twilio`. Both
    default to `mock` — nothing changes for anyone who doesn't set the
    new env vars.
  - `tests/test_notifications_core.py` (NEW) — 31 dependency-free tests:
    content-builder correctness (PNR/names/route/price/status present;
    passenger dataclass structurally has no passport field; the word
    "passport" never appears in generated text; unknown cancellation
    deadline/baggage produce the honest generic sentence with no
    fabricated number, known values are reported exactly), both Mock
    providers, and both `*DeliveryError` types.
- **Decisions/deviations from the original Proposed-section wording,
  recorded rather than silently made:**
  1. **Resend, not SMTP** — WBS-4.1 offered either. Resend was chosen
     because it has a simple, well-documented REST API needing no new
     dependency beyond `httpx` (already required); a generic SMTP
     provider would need `smtplib`/`aiosmtplib` and real mail-server
     credentials this project has never had reason to configure
     anywhere else. Not built; can be added later behind the same
     `EmailProvider` interface if the project owner prefers it.
  2. **`notifier` is optional, not a required constructor arg** — unlike
     T-3's `payment_provider` on `CancellationService` (required,
     because refund correctness is a security/money invariant every
     caller must supply), a missing notifier here just means "no
     confirmation sent," identical to every session before this one.
     Making it optional avoided forcing every non-creating
     `BookingService`/`PaymentService` construction site — and
     `CancellationService`'s internal one — to thread a dependency they
     would never use. This is a deliberate, narrower-blast-radius choice
     than T-3's, not an inconsistency; see
     `app/services/booking_service.py`/`payment_service.py`'s own
     constructor comments.
  3. **SMS only for payment links created during a live voice call, not
     every payment link** — WBS-4.4's own exit criterion is specifically
     "a payment link can actually reach a caller who can't access a
     computer mid-call." A web-created session's browser already has
     `checkout_url` on screen (see `_payment_out()`'s docstring in
     `app/api/routes/payments.py`); texting it too wasn't asked for and
     risked feeling unsolicited. Email is sent for every payment link
     regardless of channel — an unsolicited confirmation email is
     standard e-commerce practice; an unsolicited SMS is a different,
     more intrusive thing.
- **Known gap this task did not fix, found and left alone on purpose:**
  `Booking.cancellation_deadline` is a pre-existing, nullable column that
  nothing in this codebase has ever populated (`create_booking`/
  `modify_booking` never set it) — confirmed by grep before writing any
  content-builder logic, not assumed. The booking-confirmation email's
  cancellation-terms line therefore always renders the honest generic
  sentence today, never a date, through no fault of this task — fixing
  it (deciding when/how a deadline gets set) is a booking-service change
  outside T-5's scope and is **NOT** claimed as fixed here. Similarly,
  `Booking` does not persist which cabin class was booked, so this
  task's baggage lookup defaults to `CabinClass.ECONOMY` rather than the
  fare actually purchased — documented in `app/core/notifications/
  content.py` and `app/services/notification_service.py`'s docstrings,
  not silently assumed correct.
- **Testing status (§7 — stated exactly, not rounded up):**
  - **Verified locally, this session:** `cd apps/api && python3 -m
    unittest tests.test_core_logic tests.test_security_core
    tests.test_vapi_core tests.test_payments_core tests.test_api_security
    tests.test_vapi_api tests.test_notifications_core -v` → `OK`, 267
    tests, 0 failures, 0 errors, skipped=8 (the same 8 as before —
    `test_api_security.py`/`test_vapi_api.py`'s skip behavior is
    unchanged by this task). 236 pre-existing + 31 new, all new tests
    passing. Also independently confirmed via plain `python3 -c
    "import ..."` that `app.services.email_provider`,
    `app.services.sms_provider`, and `app.core.notifications.content`
    all import cleanly with neither `httpx` nor `sqlalchemy` installed
    in this sandbox, and that `app.services.notification_service`
    correctly does NOT (raises `ModuleNotFoundError: No module named
    'sqlalchemy'`, same as every other `app/services/*.py` file) — both
    checked by running them, not asserted from reading the code.
  - **Written, reviewed, cross-checked against live provider docs fetched
    this session, NOT executed:** `ResendEmailProvider`,
    `TwilioSmsProvider`, and every code path inside `BookingService`/
    `PaymentService`/`NotificationService`/the three edited routes that
    needs SQLAlchemy or FastAPI (not installed here) — same standing
    constraint as literally every other service-layer file in this
    project (T-1's Attempt log; unchanged this session, re-confirmed:
    `pip install httpx` still returns `403`).
  - **Requires external verification / BLOCKED, same class as T-1/T-4:**
    - A real `RESEND_API_KEY` + verified sending domain, and a real send
      against `POST https://api.resend.com/emails`, confirming the
      request/response shapes documented above against Resend's actual
      behavior rather than only its documentation.
    - A real `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/a purchased,
      SMS-capable `TWILIO_PHONE_NUMBER`, and a real send against `POST
      .../Messages.json`, same reasoning.
    - An end-to-end run of `create_booking`/`create_payment_session`
      with `EMAIL_PROVIDER=resend`/`SMS_PROVIDER=twilio` against a real
      Postgres database (needs the still-BLOCKED T-1 dependency stack
      too) to confirm the full wiring, not just each piece in isolation.
- **Remaining to close this task:** a project owner (or CI) with real
  network access needs to: set `RESEND_API_KEY`/`EMAIL_FROM_ADDRESS`
  and/or `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_PHONE_NUMBER`
  in the environment; flip `EMAIL_PROVIDER=resend`/`SMS_PROVIDER=twilio`;
  install `httpx` (already a listed dependency) and the rest of
  `requirements.txt` per T-1; run the full test suite once more in that
  real environment; then create one real test booking and one real test
  payment session end to end and confirm an actual email/SMS arrives
  with the expected content.

---

## Proposed (not yet authorized)

### T-2 — Decide the Phase 6/7 numbering question
- **Scope:** A decision (recorded in `docs/PROJECT_ROADMAP.md` §6.1 and
  this file), not code. Either: (a) treat "Phase 6" going forward as the
  repo's own internal label (telephony becomes an unnumbered follow-up
  to payments), or (b) restore strict spec numbering (telephony is
  Phase 6, remains open; payments is retroactively Phase 7, done).
- **NOT in scope:** renaming any existing file or handoff — those stay
  frozen regardless of the decision (see `docs/PROJECT_ROADMAP.md` §2,
  source-of-truth item 9).
- **Depends on:** nothing technical — a product/planning call.

### T-6 — Phase 9: admin dashboard
- **Scope:** `/api/v1/admin`, `/api/v1/customers`, `/api/v1/calls` API
  routes (read-heavy, RBAC-gated using the existing `ADMIN`/`SUPER_ADMIN`
  roles and `admin.*`/`calls.*` permissions — do not invent new
  permission strings without checking `rbac.py` first) + corresponding
  Next.js admin pages.
- **NOT in scope:** any change to booking/payment/Vapi business logic —
  this is read/manage surface on top of what exists.
- **Depends on:** T-1 recommended first (the RBAC HTTP layer this needs
  has never been executed either).

### T-7 — Phase 10: testing & hardening
- **Scope:** Playwright E2E suite (needs real customer-facing web pages —
  likely sequenced after T-6 or a minimal booking UI); the voice
  conversation test suite from spec §56; a full security-testing pass
  repeating `PROJECT_HANDOFF_PHASE_5.md` §11's checklist against
  whatever T-3/T-4/T-5/T-6 added.
- **Depends on:** the features it's testing existing first.

### T-8 — Close this audit's newly found gaps
- **Scope:** `update_passenger`/`get_customer`/`create_customer`/
  `update_customer`/`get_airport`/`search_airports`/`get_faq` Vapi tools
  (`docs/PROJECT_ROADMAP.md` §6.4); the audit-log actor-spoofing fix on
  the direct REST routes (§6.6); confirming whether Vapi has a native
  `end_call` capability that makes a custom tool unnecessary.
- **Depends on:** whichever of T-6 (customers) or T-4 (calls) is done
  first — several of these tools have no backing service to call until
  then.

---

## Done

### Phase 7 Milestone 1 — Payments (Stripe), labeled "Phase 6 Milestone 1" internally
- **Status:** DONE. See `docs/handoffs/2026-09-06-phase6-milestone1-payments.md`.
- **Scope delivered:** `create_payment_session`, `get_payment_status` only.
- **Authorized by:** prior session (predates this audit).

### Phase 5 — Vapi integration
- **Status:** DONE. See `PROJECT_HANDOFF_PHASE_5.md`.
- **Authorized by:** prior session (predates this audit).

### Phase 4 — Auth, RBAC & security
- **Status:** DONE. See `PROJECT_HANDOFF_PHASE_4.md`.
- **Authorized by:** prior session (predates this audit).

### Audit — Master baseline reconciliation
- **Status:** DONE (this session). Produced `docs/PROJECT_ROADMAP.md`,
  `docs/PROJECT_STATE.md`, this file, `docs/MASTER_RULES.md`,
  `docs/WORK_BREAKDOWN_STRUCTURE.md`, `docs/SESSION_PROMPT.md`; corrected
  drift in `README.md`, `docs/ARCHITECTURE.md`,
  `docs/ENVIRONMENT_VARIABLES.md`, `docs/PRODUCTION_CHECKLIST.md`. No
  source code changed.
- **Authorized by:** project owner's audit request, 2026-09-07.
