# Environment Variables

Copy `.env.example` to `.env` and fill in real values. Every variable below
is read in exactly one place: `apps/api/app/core/config.py` (`Settings`) —
**except** the `VAPI_SERVER_URL`/`VAPI_WEBHOOK_CREDENTIAL_ID`/
`VAPI_TRANSFER_NUMBER` row below, which only `scripts/setup_vapi.py` reads,
directly via `os.environ` (deliberately not through `Settings` — see that
script's own module docstring for why).

| Variable | Required? | Notes |
|---|---|---|
| `APP_ENV` | always | `development` \| `test` \| `production`. Production mode fails fast at startup if anything below marked "required in production" is missing — see `Settings.validate_for_production()`. |
| `DATABASE_URL` | always | Defaults to a local SQLite file if unset, so the app runs without Docker/Postgres in early dev. **Required in production** and must be a real `postgresql+psycopg://` URL. |
| `REDIS_URL` | required in production | Falls back to an in-process store if unset (`app/db/redis_client.py`) — fine for one dev process, not for production. |
| `SECRET_KEY` | required in production | Phase 4: HMACs CSRF tokens (`app/core/security/csrf.py`) and is the one thing every session-cookie-based CSRF check depends on — rotating it invalidates every outstanding CSRF cookie (not sessions themselves, which are looked up by their own stored hash). |
| `FIELD_ENCRYPTION_KEY` | required in production | A Fernet key (`Fernet.generate_key()`) — encrypts passport numbers at rest. Without it, passport numbers are stored with an `UNENCRYPTED-DEV:` prefix and a warning is logged on every read — this is intentionally awkward so it doesn't quietly ship to prod. |
| `BOOTSTRAP_ADMIN_ENABLED` | optional, default `false` | Phase 4. Must be `false` in production — `Settings.validate_for_production()` refuses to start otherwise. Set to `true` only for the one-time `python -m app.db.bootstrap_admin` run, then unset it. |
| `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` | required only when `BOOTSTRAP_ADMIN_ENABLED=true` | The account `bootstrap_admin.py` creates/promotes to `SUPER_ADMIN`. The password is checked against `app.core.security.password_policy` like any other — a weak one is rejected, not silently accepted because it's "just the admin". |
| `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`, `VAPI_ASSISTANT_ID`, `VAPI_PHONE_NUMBER_ID` | required in production | **Updated 2026-09-09 — T-4 authorized and `scripts/setup_vapi.py` written this session; still never run against a real account (see `docs/TASK_BOARD.md` T-4).** `VAPI_WEBHOOK_SECRET` is read by `app/core/security/vapi_webhook_auth.py` and checked on every `POST /api/v1/vapi/webhook` request before anything else happens; it's also what `setup_vapi.py` sends Vapi as `server.secret` by default. `VAPI_API_KEY` is for server-side management-API calls, used by `setup_vapi.py` — never expose it to the browser. `VAPI_ASSISTANT_ID`/`VAPI_PHONE_NUMBER_ID` are still not consumed anywhere in the running application; `setup_vapi.py` reads them (to decide create-vs-update and whether to attach a number) but has never actually been run, so no live Vapi account/Assistant has been provisioned yet — that remains the open, telephony-specific part of T-4. |
| `VAPI_SERVER_URL`, `VAPI_WEBHOOK_CREDENTIAL_ID`, `VAPI_TRANSFER_NUMBER` | required for `scripts/setup_vapi.py --apply`; unused everywhere else | **New 2026-09-09, T-4.** Not in `Settings` — read directly by `scripts/setup_vapi.py` via `os.environ`, since the running app has no use for them. `VAPI_SERVER_URL` is the full public webhook URL Vapi should call. `VAPI_WEBHOOK_CREDENTIAL_ID` is an optional override: Vapi's current docs describe a dashboard-managed "Custom Credentials" system as the primary webhook-auth mechanism now (no public API to create one was found — dashboard-only), with the older inline secret kept working under an explicit migration note; set this only if you've created a Custom Credential by hand and want `setup_vapi.py` to reference it instead of `VAPI_WEBHOOK_SECRET`. `VAPI_TRANSFER_NUMBER` is the E.164 destination for the native `transferCall` tool (docs/VAPI.md "Transfer to human") — leave blank to skip creating that tool entirely. |
| `AIRLINE_PROVIDER` | always | `mock` \| `amadeus` \| `sabre`. Defaults to `mock` — the whole system runs with zero aviation credentials this way. |
| `AIRLINE_API_BASE_URL`, `AIRLINE_API_KEY`, `AIRLINE_API_SECRET`, `AIRLINE_CLIENT_ID`, `AIRLINE_CLIENT_SECRET`, `AIRLINE_ENVIRONMENT` | required if `AIRLINE_PROVIDER != mock` | See docs/AIRLINE_PROVIDER.md. |
| `PAYMENT_PROVIDER` | always | `mock` \| `stripe`. Defaults to `mock` — mirrors `AIRLINE_PROVIDER`'s split; the whole payment flow runs with zero Stripe credentials this way. Phase 6 Milestone 1. |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | required in production **only when `PAYMENT_PROVIDER=stripe`** | Phase 6 Milestone 1: read by `app/providers/payments/stripe_provider.py` (`StripePaymentProvider`), constructed via `app/providers/payments/__init__.py`'s factory. `Settings.validate_for_production()` now checks these conditionally on `PAYMENT_PROVIDER`, same pattern as `AIRLINE_API_BASE_URL` above. Unexecuted in this sandbox (no network access to install `stripe`) — see `docs/PAYMENTS.md` §12. |
| `EMAIL_PROVIDER` | always | `mock` \| `resend`. Defaults to `mock` — mirrors `AIRLINE_PROVIDER`/`PAYMENT_PROVIDER`'s split. **New 2026-09-09, T-5.** |
| `EMAIL_FROM_ADDRESS`, `RESEND_API_KEY` | required in production **only when `EMAIL_PROVIDER=resend`** | **Updated 2026-09-09, T-5** (previously "unused until Phase 8" — Phase 8 is now built). Read by `app/services/email_provider.py` (`ResendEmailProvider`), constructed via that module's `get_email_provider()` factory. `Settings.validate_for_production()` checks both conditionally on `EMAIL_PROVIDER`, same pattern as `STRIPE_SECRET_KEY` above. Unexecuted in this sandbox (no network access to install `httpx` or reach `api.resend.com`) — see `docs/PAYMENTS.md` §8/§12 and `docs/TASK_BOARD.md`'s T-5 entry. |
| `SMS_PROVIDER` | always | `mock` \| `twilio`. Defaults to `mock`, same split. **New 2026-09-09, T-5.** |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | required in production **only when `SMS_PROVIDER=twilio`** | **Updated 2026-09-09, T-5** (previously "unused until Phase 8"). Read by `app/services/sms_provider.py` (`TwilioSmsProvider`). `TWILIO_PHONE_NUMBER` must be a real, SMS-capable, purchased Twilio number — not just any string. Same unexecuted-in-this-sandbox caveat as `RESEND_API_KEY` above. |
| `FRONTEND_URL`, `CORS_ORIGINS` | always | Comma-separate multiple origins in `CORS_ORIGINS`. |
| `NEXT_PUBLIC_API_URL` | web app only | Where the Next.js dev server proxies `/api/*` to (see `next.config.js`). |
| `SENTRY_DSN` | optional | Not wired up to anything yet — no Sentry SDK call exists in this phase. |
| `LOG_LEVEL` | optional, default `INFO` | Passed to `structlog`. |
| `CALL_TRANSCRIPT_RETENTION_DAYS`, `CALL_RECORDING_RETENTION_DAYS`, `AUDIT_LOG_RETENTION_DAYS` | optional | Defined and defaulted; no cleanup job reads them yet (§65 retention enforcement is not implemented). |
| `CALL_RECORDING_ENABLED`, `RECORDING_DISCLOSURE_MESSAGE` | optional | The Vapi call layer itself has landed (Phase 5), but call recording/transcription specifically has not been built on top of it (spec §21–22/§67) — these remain defined and unused. |

A variable listed here with "unused until Phase N" exists in `Settings`
(so `.env.example` matches the full spec and nothing needs renaming
later) but nothing in the current codebase reads it yet — don't spend time
filling it in until you're actually building that phase.
