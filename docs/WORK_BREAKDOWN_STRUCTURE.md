# Charter123 — Work Breakdown Structure

Decomposition of `docs/PROJECT_ROADMAP.md` §7's execution plan into
concrete, sequenced tasks. This is decomposition, not authorization —
check `docs/TASK_BOARD.md` before starting anything below.

Numbering here is independent of the Master Build Prompt's phase numbers
(preserved untouched in the roadmap) — think of this as "the next N
things to do," cross-referenced to which original phase each belongs to.

---

## WBS-1 — Full-stack verification (blocks nothing, blocked by nothing but network access)

Corresponds to: cross-cutting, unblocks verifying Phases 4–7's HTTP
layers simultaneously.

1.1. Install `apps/api/requirements.txt` in a networked environment.
1.2. Run `python3 -m unittest tests.test_api_security tests.test_vapi_api
     -v` — expect these to actually execute for the first time ever.
1.3. Fix any real bugs found (expected — every previous phase that got a
     chance to actually execute found at least one; see
     `PROJECT_HANDOFF_PHASE_4.md`/`_5.md` §12).
1.4. `docker compose up --build` for the first time; fix whatever breaks.
1.5. `alembic upgrade head` against real Postgres; confirm migrations
     `0001`→`0004` apply cleanly in sequence.
1.6. `python -m app.db.seed`; confirm airport/aircraft data loads.
1.7. Update `docs/PROJECT_STATE.md`'s "Verified" columns from 🟡/written
     to ✅/executed wherever this closes the gap.

**Exit criteria:** the 223 dependency-free tests plus the two previously-
skipping HTTP suites all pass against a real stack; `docker compose up`
succeeds; migrations apply cleanly.

**Test requirements:** all of the above, executed, not just attempted.

---

## WBS-2 — Phase 6 remainder: telephony

Corresponds to: original Master Build Prompt Phase 6 (minus the parts
already delivered as Phase 5's Vapi tool logic — see roadmap §6.1).

2.1. Write `scripts/setup_vapi.py` (spec §51): create/update the 21
     registered tools from `tool_schemas.py` on a real Vapi account,
     create/update the Assistant, configure the webhook server URL +
     shared secret, attach tools, optionally attach a phone number.
     Read from environment variables; never hard-code an assistant ID.
2.2. Configure a native Vapi `transferCall` tool per `docs/VAPI.md`'s
     "Transfer to human" section; attach it alongside the custom tools.
2.3. Connect a real phone number to the Assistant.
2.4. Place one real inbound test call; verify `Call`/`ToolExecution` rows
     are created correctly and `endedReason` is captured on
     `end-of-call-report`.
2.5. Verify `transfer_to_human` → native transfer end-to-end (this is
     the one behavior `docs/VAPI.md` marks "PARTIALLY IMPLEMENTED —
     EXTERNAL VAPI VERIFICATION REQUIRED"; this closes it for real).

**Dependencies:** WBS-1 recommended first (HTTP layer should be known-
working before adding a live external caller to it). A live Vapi account.

**Exit criteria:** one real phone call reaches the assistant, searches a
flight, and the call is correctly recorded; one real transfer completes
and is observable via `Call.ended_reason`.

**Security constraints:** do not weaken `VAPI_ASSISTANT_PERMISSIONS` or
`TOOL_AUTHORIZATION_MATRIX` to make a live call "work" — if something is
denied that should be allowed, fix the matrix deliberately and re-run
`tests/test_vapi_core.py`, don't bypass it.

---

## WBS-3 — Phase 7 remainder: payments

Corresponds to: original Master Build Prompt Phase 7, remainder after
Milestone 1 (`docs/handoffs/2026-09-06-phase6-milestone1-payments.md`).

3.1. Implement `refund_payment` (already reserved `STAFF_OR_ADMIN_ONLY`
     in `TOOL_AUTHORIZATION_MATRIX` — do not add a new permission string
     without checking `rbac.py` first; `payments.refund` already exists).
3.2. Fix `CancellationService.cancel()` (see inline comment + `docs/
     PAYMENTS.md` §9) to actually call `PaymentProvider`/`refund_payment`
     logic when flipping a `PAID` booking to `REFUNDED`, instead of only
     updating the local field.
3.3. A real Stripe test-mode Checkout Session, completed end-to-end,
     with a real webhook delivery via `stripe listen` or a configured
     endpoint (needs WBS-1's network access).
3.4. PCI-relevant configuration review in the Stripe Dashboard (domain,
     branding, webhook endpoint) — human task, not code.

**NOT in scope for 3.1–3.2:** payment-link delivery — that's WBS-4.

**Dependencies:** WBS-1 (network access); a Stripe test-mode account.

**Exit criteria:** a staff/admin actor can refund a payment through the
same two-gate authorization pattern (`authorize_payment_access`/
`REQUIRES_VERIFIED_BOOKING`) documented in `docs/PAYMENTS.md` §6; a
cancelled, previously-paid booking triggers a real refund, not just a
local status flip.

---

## WBS-4 — Phase 8: notifications

Corresponds to: original Master Build Prompt Phase 8.

4.1. Implement a real email provider (Resend, per `.env.example`'s
     `RESEND_API_KEY`, or configurable SMTP) behind the existing
     `EmailProvider`-shaped interface `MockEmailProvider` already
     implements — don't change the interface shape without reason.
4.2. Implement a real SMS provider (Twilio, per `.env.example`'s
     `TWILIO_*` variables) — this is new; no interface exists yet, so
     design one mirroring the email provider's shape.
4.3. Wire booking-confirmation delivery (spec §44: PNR, passenger names,
     itinerary, flight numbers, dates, baggage allowance, payment status,
     cancellation terms — **never passport numbers**).
4.4. Wire payment-link delivery for `create_payment_session`'s Checkout
     URL — this is the fix for the gap `docs/PAYMENTS.md` §8 documents
     ("a phone caller who needs the link delivered has no path to
     receive it today except a human transfer").

**Dependencies:** email/SMS provider credentials.

**Exit criteria:** a real booking triggers a real email; a payment link
can actually reach a caller who can't access a computer mid-call.

**Security constraints:** never send passport numbers in a notification;
redact/mask the same way voice responses already do.

---

## WBS-5 — Phase 9: admin dashboard

Corresponds to: original Master Build Prompt Phase 9.

5.1. `/api/v1/customers` routes (get/create/update) — this also closes
     part of this audit's §6.4 finding (no customer-facing tool has a
     backing service to call yet).
5.2. `/api/v1/calls` routes (list/read `Call`/`ToolExecution` data,
     gated by the existing `calls.read`/`calls.manage` permissions —
     already defined, never used).
5.3. `/api/v1/admin` routes for bookings/payments/analytics as scoped by
     spec §32–34, gated by `ADMIN`/`SUPER_ADMIN` + relevant `*.read`
     permissions.
5.4. Next.js admin pages consuming the above — calls, bookings,
     customers, payments, analytics per spec §32.
5.5. Revisit this audit's §6.4 finding (`update_passenger`, `get_
     customer`/`create_customer`/`update_customer` as Vapi tools) now
     that 5.1 gives them a backing service — add the Vapi tool schemas +
     authorization matrix entries + dispatch functions, following the
     exact pattern every existing tool uses (see `docs/MASTER_RULES.md`
     §6).

**Dependencies:** WBS-1 recommended (RBAC HTTP layer this needs has never
executed either).

**Exit criteria:** a staff user can log in, see a real call's transcript
metadata and tool executions, see a booking's full audit trail, and see
basic revenue/conversion analytics — all correctly RBAC-gated (verify a
`SUPPORT_AGENT` cannot reach `payments.refund`-gated views, etc.).

**Security constraints:** every new route needs an explicit permission
check — do not add a route that's reachable by any authenticated user by
default. Mask sensitive data in list views per spec §33.

---

## WBS-6 — Phase 10: testing & hardening

Corresponds to: original Master Build Prompt Phase 10.

6.1. Playwright E2E suite (spec §55): search → book → lookup → cancel →
     modify → human transfer, against a running web+api stack. Needs
     real customer-facing web pages first (currently only a status page
     + auth pages exist) — likely sequenced after a minimal booking UI
     lands, whether that's part of WBS-5 or its own small task.
6.2. Voice conversation test suite (spec §56) — the 7 example test cases
     in the spec (missing-info collection, verify-before-cancel, no
     booking without a quote, quote-only on price question, human
     transfer on request, never reveal passport number) plus whatever
     else the Assistant's real behavior surfaces once WBS-2 gives it a
     live phone number to test against.
6.3. Repeat `PROJECT_HANDOFF_PHASE_5.md` §11's full security-review
     checklist against whatever WBS-2 through WBS-5 added.
6.4. Close this audit's own findings not already covered above: the
     audit-log actor-spoofing gap (`docs/PROJECT_ROADMAP.md` §6.6),
     `RATE_LIMIT_PROFILES` tuning against real traffic (needs WBS-2's
     live call volume to have real numbers to tune against), and a
     decision on whether Vapi has a native `end_call` capability making
     a custom tool unnecessary (`docs/PROJECT_ROADMAP.md` §6.4).
6.5. GDPR export/deletion endpoints (spec §66) and retention-policy
     enforcement jobs (the `*_RETENTION_DAYS` settings already exist;
     nothing reads them yet).
6.6. i18n (German/Persian voice support, spec §41) — needs a translated
     system prompt, a language-detection or explicit-selection strategy,
     and per-language TTS/STT configuration in the Vapi Assistant.

**Dependencies:** the features each sub-task tests must exist first.

**Exit criteria:** spec §79's full 34-item Definition of Done is either
✅ or has an honestly-labeled, specific reason it isn't (never a vague
"mostly done").
