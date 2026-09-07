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

### T-3 — Phase 7 remainder: `refund_payment`
- **Scope:** Implement the reserved, `STAFF_OR_ADMIN_ONLY` `refund_payment`
  tool/route against `PaymentProvider`, and fix `CancellationService.
  cancel()`'s local-only `REFUNDED` flip (see `docs/PAYMENTS.md` §9) to
  actually call it when a paid booking is cancelled.
- **NOT in scope:** payment-link delivery (T-5), telephony (T-4).
- **Depends on:** T-1 recommended first; a Stripe test-mode account for
  end-to-end verification.

### T-4 — Phase 6 remainder: telephony
- **Scope:** `scripts/setup_vapi.py` (spec §51: create/update tools,
  create/update assistant, configure webhook, attach a phone number);
  connect a real number; one real inbound test call; configure the
  native `transferCall` tool per `docs/VAPI.md`'s instructions.
- **NOT in scope:** any change to existing tool logic — this is
  configuration/scripting only, on top of what Phase 5 already built.
- **Depends on:** a live Vapi account.

### T-5 — Phase 8: notifications
- **Scope:** A real email provider (Resend or SMTP) and a real SMS
  provider (Twilio), wired to booking-confirmation and payment-link
  delivery. Replaces `MockEmailProvider` with a real implementation
  behind the same interface — do not change the interface shape without
  reason.
- **NOT in scope:** admin dashboard (T-6).
- **Depends on:** provider credentials.

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
