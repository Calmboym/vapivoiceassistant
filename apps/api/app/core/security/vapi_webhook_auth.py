"""
Vapi webhook request authentication (Phase 5).

Deliberately dependency-free (stdlib `hmac`/`hashlib` only) so it can be
imported and unit-tested without FastAPI present — same discipline as the
rest of app/core/security/*.py (see tests/test_security_core.py).

THIS IS THE OUTER TRUST BOUNDARY FOR THE ENTIRE VAPI CHANNEL. Nothing in
app/core/security/vapi_authorization.py matters if a request that never
came from Vapi at all can reach the tool-call dispatcher — see §13:
"Vapi is not the source of truth" starts with "is this even Vapi."

Verified against Vapi's current documented auth model (docs.vapi.ai/
server-url/server-authentication, cross-checked while building this
phase, September 2026): a fresh Server URL has NO authentication by
default — auth is opt-in, configured per-assistant/tool/phone-number/org.
The mechanism this module implements is the shared-secret model, which is
what Charter123's existing single `VAPI_WEBHOOK_SECRET` setting
(app/core/config.py, already present since Phase 4) naturally maps onto:
Vapi sends the configured secret verbatim in an `X-Vapi-Secret` header
(legacy inline `server.secret` field) or as `Authorization: Bearer
<secret>` (the newer Custom Credentials "Bearer Token" mechanism,
configured to reproduce the same legacy behavior). Both are a literal
shared-secret comparison — nothing is hashed or HMAC-signed by Vapi
itself in this mode, so this module does not attempt to verify an
HMAC-over-body signature. If a deployment later configures Vapi's
"HMAC signature-based authentication" Custom Credential instead, this is
the function to extend — it is intentionally the only place that reads
either header, so upgrading the mechanism means changing one function,
not every call site.

Fails closed: any missing secret (server misconfigured), missing header
(request didn't present one), or mismatch is REJECTED. There is no mode
where a webhook request is accepted without a configured, matching
secret — `Settings.validate_for_production()` already refuses to boot in
production without `VAPI_WEBHOOK_SECRET` set (app/core/config.py, Phase
4), and this module refuses to treat an unset secret as "verification not
required."
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class WebhookAuthResult:
    authenticated: bool
    reason: str


def _extract_presented_secret(headers: Mapping[str, str]) -> Optional[str]:
    """Headers are matched case-insensitively — HTTP header names are
    case-insensitive by spec, and different HTTP stacks normalize them
    differently (FastAPI/Starlette's Headers object already does this;
    this function does its own lowercasing so it also works against a
    plain dict in tests, without assuming a specific framework's header
    container type).

    `X-Vapi-Secret` (legacy inline `server.secret`) is checked first, then
    `Authorization: Bearer <secret>` (Custom Credentials, configured to
    reproduce the same shared-secret behavior) — see module docstring."""
    lowered = {k.lower(): v for k, v in headers.items()}

    secret_header = lowered.get("x-vapi-secret")
    if secret_header:
        return secret_header

    auth_header = lowered.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[len("bearer "):].strip()

    return None


def verify_webhook_request(headers: Mapping[str, str], *, configured_secret: Optional[str]) -> WebhookAuthResult:
    """The single function app/api/routes/vapi.py calls before parsing a
    single field of the request body. Never raises.

    `configured_secret` is `settings.vapi_webhook_secret` — passed in
    rather than read from settings here so this stays dependency-free and
    testable with an arbitrary fake secret, matching how
    app/core/security/csrf.py takes `secret_key` as a parameter rather
    than importing config.py directly.
    """
    if not configured_secret:
        # Fail closed on a misconfigured server, not open. A deployment
        # with no secret configured is not "publicly-intended," it's
        # broken — see Settings.validate_for_production(), which already
        # refuses to boot in production without one.
        return WebhookAuthResult(False, "webhook_secret_not_configured")

    presented = _extract_presented_secret(headers)
    if not presented:
        return WebhookAuthResult(False, "no_secret_presented")

    # Constant-time comparison — a naive `==` here would leak the secret
    # one byte at a time via response-timing, the same class of bug
    # app/core/security/tokens.py's verify_token() already guards against
    # for session/verification tokens.
    if not hmac.compare_digest(presented, configured_secret):
        return WebhookAuthResult(False, "secret_mismatch")

    return WebhookAuthResult(True, "ok")
