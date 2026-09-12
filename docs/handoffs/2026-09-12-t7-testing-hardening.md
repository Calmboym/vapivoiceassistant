# Handoff: T-7 — Phase 10: testing & hardening

## 1. Current project position

This session executed T-7 (`docs/TASK_BOARD.md`), authorized by the
project owner's explicit instruction ("Execute and authorize T-7 from
TASK-BOARD.md"), the same mechanism T-4/T-5/T-6 used. T-7 covers
WBS-6.1/6.2/6.3 only (`docs/WORK_BREAKDOWN_STRUCTURE.md`) — not 6.4
(audit-log actor-spoofing fix, T-8's scope), not 6.5 (GDPR) or 6.6
(i18n). Before touching anything, this session read, in order:
`docs/PROJECT_ROADMAP.md` (full), `docs/PROJECT_STATE.md` (full),
`docs/TASK_BOARD.md` (T-7's entry + surrounding context),
`docs/MASTER_RULES.md` (full), `docs/WORK_BREAKDOWN_STRUCTURE.md` §WBS-6,
and `docs/handoffs/PROJECT_HANDOFF_PHASE_5.md` §11 (the security-review
checklist T-7 is required to repeat). The baseline test count (289
passing, 8 skipped) was re-run and confirmed to match the documentation
exactly before any change was made.

## 2. Completed work

Three scope items, all substantively done; see §12 for the one genuinely
incomplete piece (customer-facing Playwright coverage) and why.

1. **Admin-facing Playwright E2E suite** (`tests/e2e/admin/`, WBS-6.1) —
   written against the real `apps/web/app/admin/**` component source: the
   `/login` → `/admin` redirect gate, dashboard section headings, nav
   between all four sections with active-link assertion, and each of
   bookings/customers/calls' table columns + row-to-detail navigation.
2. **Voice conversation test suite** (`apps/api/tests/test_voice_
   conversation_core.py`, WBS-6.2) — 29 dependency-free tests, one class
   per spec-§56 scenario, executed and passing.
3. **Security-testing pass** (WBS-6.3) — `PROJECT_HANDOFF_PHASE_5.md`
   §11's twelve-category checklist repeated against T-3/T-4/T-5/T-6's
   code.

Two real, concrete bugs were found and fixed along the way (not
hypothetical, not pattern-matched — each confirmed by direct inspection
of the affected code):

- `apps/web/app/login/page.tsx` silently ignored the `next=` query
  parameter that `apps/web/app/admin/layout.tsx` depends on
  (`/login?next=/admin`), always landing on `/account` regardless. Found
  while writing the Playwright login test.
- `app/core/encryption.py` imported `app.core.config`/`app.core.logging`
  at module level even though `mask_for_speech()` — the function the
  "never reveal passport number" spec-§56 scenario depends on — needs
  neither. Since pydantic/structlog are not installed in this (or any)
  sandbox this project has run in, this function had never once been
  importable by this project's own dependency-free test tier before
  today. Found while writing the voice-conversation suite.

One more real finding from the security pass, also fixed:

- `notification_service.py`'s three delivery-failure audit calls stored
  the provider's raw `message` string in `AuditLog.event_metadata`
  alongside `error_code`. Twilio's documented error codes 21211/21614
  ("Invalid 'To'/'From' Phone Number") and Resend's field-validation
  errors both echo the rejected input back inside that message text —
  meaning a delivery failure could put a customer's own phone number or
  email address into a log field, which T-6's new admin audit-trail
  endpoint renders verbatim. `error_message` dropped from all three call
  sites; `error_code` (a bounded, provider-defined value, not
  request-echoed free text) kept.

## 3. Files created

- `apps/api/tests/test_voice_conversation_core.py` — 29 tests, 6 classes
  (one per spec-§56 scenario named in WBS-6.2).
- `tests/e2e/admin/package.json`, `tests/e2e/admin/playwright.config.ts`,
  `tests/e2e/admin/tests/fixtures.ts`,
  `tests/e2e/admin/tests/auth-gate.spec.ts`,
  `tests/e2e/admin/tests/navigation.spec.ts`,
  `tests/e2e/admin/tests/sections.spec.ts`, `tests/e2e/admin/README.md`.
- `docs/handoffs/2026-09-12-t7-testing-hardening.md` (this file).

## 4. Files modified

- `apps/api/app/core/encryption.py` — lazy-imported `get_settings`/
  `get_logger` (see §2). Behavior of `encrypt_sensitive`/
  `decrypt_sensitive` unchanged.
- `apps/api/app/services/notification_service.py` — dropped
  `error_message` from three audit-metadata call sites (see §2 and §9).
- `apps/web/app/login/page.tsx` — now reads and honors an internal `next`
  redirect target after login, wrapped in the `<Suspense>` boundary the
  Next.js App Router requires for `useSearchParams()` (see §5, §9).
- `tests/e2e/README.md`, `tests/voice/README.md` — updated from
  placeholder text to reflect what now exists and what's still blocked.
- `docs/PROJECT_STATE.md` — new rows/section for T-7's fixes and the
  updated Testing table (289 → 318).
- `docs/TASK_BOARD.md` — full T-7 entry (moved from its old placeholder
  position between T-2/T-8 to sit after T-6, matching where T-3/T-4/T-5/
  T-6's completed entries live).
- `docs/PROJECT_ROADMAP.md` §8 (Current position) — new T-7 bullet,
  updated "Current authorized work"/"Next work"/"Important known risks"
  lists.
- `docs/WORK_BREAKDOWN_STRUCTURE.md` WBS-6 — status annotations on
  6.1/6.2/6.3.
- `.github/workflows/t1-verify.yml` — added
  `tests.test_voice_conversation_core` to the pinned command; `EXPECTED`
  289 → 318 with a dated history comment, same style as the existing
  223→236→267→289 chain.

## 5. Architecture changes

None. No new service, model, migration, or API route was introduced.
`apps/web/app/login/page.tsx`'s internal restructuring (splitting into a
`LoginForm` component wrapped by a `<Suspense>` boundary) is the one
structural change, and it's a Next.js App Router requirement for reading
`useSearchParams()`, not a design choice — no other behavior changed.

## 6. Database changes

None.

## 7. API changes

None. No route signature, request/response schema, or status code
changed.

## 8. Integration changes

None. No new external provider, webhook, or third-party dependency was
introduced. `tests/e2e/admin/package.json` adds `@playwright/test` as a
devDependency scoped to that suite only — not a dependency of the
running application.

## 9. Security changes

Two fixes, detailed in §2:

1. `notification_service.py`'s audit-metadata PII leak (WBS-6.3
   finding) — see §2 for the mechanism. This closes a genuine gap in the
   same redaction discipline `ToolExecution.arguments_redacted` and
   `customer_service.py`'s "field names only" audit pattern already
   established elsewhere in this codebase; it doesn't introduce a new
   pattern, it extends an existing one to a spot the T-5 session missed.
2. `apps/web/app/login/page.tsx`'s redirect-target handling — not a
   security fix per se (the original bug was a UX/functional regression,
   not a vulnerability), but implemented with an open-redirect guard
   regardless: `next` is only honored when it starts with `/` and not
   `//` (the protocol-relative-URL shape), falling back to `/account`
   otherwise.

**Full §11 checklist-by-checklist result**, repeated against T-3
(payments.py's refund route)/T-4 (scripts/setup_vapi.py)/T-5
(email_provider.py, sms_provider.py, notification_service.py)/T-6
(customers.py, calls.py, admin.py, authorize_staff_access(),
require_staff_permission()):

- **Authentication bypass:** no changes found. New admin/customer/call
  routes all require a dependency-injected authenticated actor before
  reaching the route body; no client-supplied identity header is trusted
  for authorization anywhere reviewed.
- **Authorization bypass/IDOR/privilege escalation:** no new issue.
  `customers.py`'s `get_customer`/`update_customer` fetch the row by the
  URL's `customer_id` first, then check `require_customer_profile_access`
  against the DB-derived customer's own ID — the resource-then-authorize
  pattern established in Phase 4, correctly reused, not bypassed.
- **SSRF:** none. `scripts/setup_vapi.py`, `email_provider.py`, and
  `sms_provider.py` all call fixed, hardcoded HTTPS hosts (Vapi's API
  base, `https://api.resend.com/emails`, Twilio's
  `api.twilio.com/.../Accounts/{account_sid}/...` — `account_sid` is a
  public-ish identifier interpolated into a path, not a
  user-controllable host) — no request target is ever built from
  caller-supplied input.
- **Replay attacks:** T-3's refund route requires `confirmed=True`
  (MASTER_RULES §3's pattern), same as `create_booking`/`cancel_booking`/
  `create_payment_session`. No new replay surface found.
- **Webhook spoofing:** none of T-3/T-4/T-5/T-6 add a new inbound
  webhook receiver — Resend/Twilio delivery-status webhooks were not
  built (see §12), so there's no new signature-verification surface to
  have gotten wrong. The pre-existing Vapi/Stripe webhook auth is
  untouched by any of these four tasks.
- **Secret leakage:** reviewed `email_provider.py`, `sms_provider.py`,
  `scripts/setup_vapi.py` — API keys/tokens are only ever placed in
  `Authorization` headers or an `auth=` tuple (Twilio, via httpx), never
  interpolated into a printed/logged string anywhere in these files.
- **PII leakage:** the one real finding, fixed (see §2). Everything else
  reviewed was already clean: `notification_service.py`'s *other* audit
  entries (`{"channel": ...}` only), `customer_service.py`'s
  `fields_changed` list (field names, never values),
  `booking_service.py`'s `changes.keys()` (same pattern),
  `calls.py`'s use of `arguments_redacted` rather than raw tool
  arguments.
- **Tool injection:** N/A for these four tasks — `refund_payment` is
  staff/admin-only (`STAFF_OR_ADMIN_ONLY` always denies `VAPI_AGENT`),
  never a Vapi-invokable tool, closing off the one path that would have
  made this relevant.
- **Prompt injection via tool responses:** N/A — none of T-3/T-5/T-6 add
  a new Vapi tool response. T-4's `setup_vapi.py` sends static, hardcoded
  system-prompt/tool-description strings to Vapi at setup time, not
  strings built from live user data — no injection vector.
- **Unsafe mutation execution/missing confirmation:** T-3's
  `refund_payment` correctly requires `confirmed=True`, mirroring
  `cancel_booking`/`create_payment_session`. T-6's one new mutating
  endpoint (`update_customer`, a contact-info correction) is not held to
  MASTER_RULES §3's confirmation-pattern bar — that rule names booking/
  cancellation/payment specifically, and a staff member correcting a
  phone number isn't in that category. No gap.
- **Rate-limit bypass:** reviewed and found genuinely absent on T-6's
  new routes (`customers.py`, `calls.py`, `admin.py`) — unlike
  `bookings.py`/`auth.py`/the Vapi webhook, which all use
  `app/core/security/rate_limiter.py`. Not treated as a fix-required gap
  this session: every admin route requires staff authentication + a
  specific RBAC permission already, a smaller and more accountable
  population than the unauthenticated public surfaces rate limiting
  protects elsewhere. Recorded in `docs/PROJECT_STATE.md`'s "Known
  residual security/integrity findings" as a reviewed-and-accepted item,
  in case the project's threat model later wants to cover a compromised
  staff credential being used for bulk scraping.
- **Insecure logging/error leakage:** the `notification_service.py`
  finding above. One sibling instance reviewed and deliberately NOT
  changed: `cancellation_service.py`'s `payment.refund_failed_during_
  cancellation` audit entry stores a raw `str(exc)` from a
  `PaymentProviderError` (Stripe) — plausibly the same shape of issue,
  but not independently confirmed against live Stripe error text the way
  Twilio's/Resend's documented formats were checked for this task's two
  actual providers. Fixing a confirmed instance and an unconfirmed,
  different-provider sibling with the same one-line change felt like
  generalizing from a pattern rather than evidence; recorded instead of
  silently patched or silently ignored.

## 10. Tests executed — exact results

```
cd apps/api && python3 -m unittest \
  tests.test_core_logic tests.test_security_core tests.test_vapi_core \
  tests.test_payments_core tests.test_notifications_core \
  tests.test_admin_core tests.test_voice_conversation_core -v
```
→ `Ran 318 tests ... OK` (0 failures, 0 errors). 289 pre-existing
(T-1 baseline through T-6) + 29 new, all in the new
`tests.test_voice_conversation_core`.

```
cd apps/api && python3 -m unittest tests.test_api_security tests.test_vapi_api -v
```
→ skip cleanly, `skipped=8`, unchanged from the T-6 baseline — no
regression to the skip behavior itself.

```
python3 -c "from app.core.encryption import mask_for_speech; print(mask_for_speech('X1234567'))"
```
→ succeeded, printed `****4567`. Before this session's fix, the
equivalent import raised `ModuleNotFoundError: No module named
'pydantic'`.

TypeScript syntax check (standalone `tsc`, same harness T-6 established —
`--skipLibCheck`, no `node_modules` since `npm install` has never been
possible in any sandbox this project has used):
```
tsc --noEmit --ignoreConfig --jsx react-jsx --esModuleInterop --skipLibCheck \
  --target es2020 --moduleResolution node <file>
```
run against `apps/web/app/login/page.tsx` and all four new `.ts` files
under `tests/e2e/admin/`. Zero genuine syntax errors in any of them —
only expected missing-module noise (`Cannot find module '@/contexts/
AuthContext'`, `'@playwright/test'`, etc.) and a deprecation notice about
the `moduleResolution` flag itself, neither of which reflects a real
problem in the code.

## 11. Runtime verification status

- **Verified locally, this session:** everything in §10 above.
- **Written, reviewed, NOT executed (needs SQLAlchemy/FastAPI — not
  installed in this or any sandbox this project has run in):**
  `notification_service.py`'s audit-metadata fix itself (the module has
  never been importable in this sandbox's dependency-free tier, same
  standing constraint as every other service-layer file since T-1).
- **Written, syntax-checked, NOT type-checked against a real toolchain,
  NOT executed (no Node network access to `npm install`
  `@playwright/test` in this or any sandbox to date):** all of
  `tests/e2e/admin/`, and `apps/web/app/login/page.tsx`'s modification.
- **Requires external verification / BLOCKED, same class as T-1:**
  - `npm install` in an environment with real network access, then `npx
    playwright test` against a real running web+api+db stack with a
    bootstrapped staff account (`tests/e2e/admin/README.md` has the
    exact steps and env vars).
  - WBS-2.2-2.5's live Vapi phone number, for the voice-conversation
    suite's other half (the live assistant's actual conversational
    behavior) — unchanged, still blocked on a real Vapi account.

## 12. Known limitations (this session)

The customer-facing half of the Playwright E2E suite (search → book →
lookup → cancel → modify → human transfer, spec §55) was not built.
Confirmed by direct inspection that `apps/web/app/` contains only
`account/`, `admin/`, `login/`, `register/`, and a status `page.tsx` — no
search, booking, lookup, cancellation, or modification screen exists
anywhere in this codebase. Writing Playwright specs against routes and
selectors that don't exist would mean fabricating a UI to test against,
which both this task's own instructions and MASTER_RULES.md's "never
fabricate" principle rule out. `docs/WORK_BREAKDOWN_STRUCTURE.md`'s
WBS-6.1 had already flagged this exact sequencing question as open
("whether that's its own small task or folds into WBS-6 itself") before
this session started; this session did not resolve it by building a
customer booking UI as an unauthorized scope expansion under a "testing
& hardening" task. It remains open — see §17.

## 13. Blocked items

- WBS-2.2-2.5 (live Vapi phone number/inbound call/`transferCall`
  verification) — unchanged by this task, still blocked on a real Vapi
  account.
- `tests/e2e/admin/`'s actual execution — blocked on `npm install` (no
  Node network access) and a live web+api+db stack with a bootstrapped
  staff account.
- `notification_service.py`'s fix — blocked on FastAPI/SQLAlchemy
  installation, same as every other service-layer file in this project.

## 14. Deferred items (explicitly out of this session's scope)

- WBS-6.4 (audit-log actor-spoofing fix, `RATE_LIMIT_PROFILES` tuning,
  the `end_call` native-capability decision) — T-8's scope, untouched.
- WBS-6.5 (GDPR export/deletion) and WBS-6.6 (i18n) — not started,
  outside T-7's authorized scope.
- The customer-facing booking UI needed to unblock the rest of WBS-6.1 —
  see §12 and §17.
- Generalizing the `notification_service.py` audit-metadata fix to
  `cancellation_service.py`'s Stripe-refund-failure entry — see §9's
  last bullet.
- Adding rate limiting to T-6's new admin routes — see §9's rate-limit
  bullet.

## 15. Pre-existing issues discovered but NOT fixed (out of authorized scope)

- `cancellation_service.py`'s `payment.refund_failed_during_cancellation`
  audit entry stores a raw `str(exc)` from a Stripe `PaymentProviderError`
  — plausibly the same PII-leak shape this task fixed for Twilio/Resend,
  not independently confirmed. See §9.
- T-6's admin routes carry no rate limiting — reviewed, not treated as a
  gap requiring a fix given the staff-authenticated, RBAC-gated
  population. See §9.

Neither of these was introduced by this session; both were found while
doing WBS-6.3's review and are recorded rather than silently fixed or
silently ignored, per this project's established documentation
discipline.

## 16. Remaining work within the project

1. A product/planning decision on the customer-facing booking UI's
   sequencing (§12) — once it exists, the rest of `tests/e2e/`'s
   customer-flow half can be written the same way the admin half was
   this session.
2. The `npm install`/live-Vapi-account items in §13, once this project
   runs somewhere with that access — same standing item as
   T-1/T-4/T-5/T-6.
3. T-2 (Phase 6/7 numbering) and T-8 (Vapi tools, audit-log
   actor-spoofing fix) remain open, unaffected by this task.
4. The two items in §15, if the project owner wants them addressed.

## 17. Recommended next step

Two independent tracks, neither blocking the other:

- **If network/infra access becomes available:** run WBS-1's full stack
  install and execute the full HTTP-level test suite for real — this now
  additionally validates T-7's `notification_service.py` fix and gives
  `tests/e2e/admin/` something real to run against for the first time.
- **If not:** the highest-value next step is a product decision on the
  customer-facing booking UI (§12/§16.1) — until that's decided, WBS-6.1
  cannot fully close, and it's a planning call, not something further
  code archaeology in this sandbox can resolve on its own. T-8 (Vapi
  tools, unblocked since T-4/T-6) is the next fully-actionable
  code task if a decision on the UI isn't made yet.

## 18. Anything the next session must know

- Read `docs/TASK_BOARD.md`'s T-7 entry in full before assuming any part
  of Phase 10 is "done" — it's precisely three-fifths done (6.1 partial,
  6.2 and 6.3 done, 6.4-6.6 not this task's scope at all).
- `tests/voice/` (the directory) is still just a `README.md` pointing
  elsewhere — the actual voice-conversation suite lives in
  `apps/api/tests/test_voice_conversation_core.py`, dependency-free, next
  to the other `*_core.py` suites it shares an import surface with. Don't
  go looking for test code in `tests/voice/` itself.
- The "7 example test cases" WBS-6.2 names for spec §56 is a
  pre-existing count/list mismatch in this repo's own documentation (only
  six are ever named) — this session did not invent a seventh case to
  make the number line up, and neither should a future one, absent the
  actual original spec text to check against (it isn't committed
  anywhere in this repo — see `docs/PROJECT_ROADMAP.md`'s "Required
  reading" note on why).
- `apps/web/app/login/page.tsx` is the first file in this codebase to use
  `useSearchParams()` — it's wrapped in a `<Suspense>` boundary per
  Next.js's own documented requirement for that hook in the App Router.
  If a future session adds `useSearchParams()` elsewhere, match that
  pattern rather than reinventing it.
