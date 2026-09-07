"""
CSRF protection for cookie-authenticated browser requests (Phase 4 spec
§19).

Mechanism: signed double-submit cookie.
  1. On session creation, the server generates a random CSRF secret and
     sends it to the browser in a *readable* (non-HttpOnly) cookie, HMAC'd
     with the server's SECRET_KEY and bound to the session id so a token
     minted for one session can't be replayed against another.
  2. The frontend JS reads that cookie and echoes its value back in a
     custom request header (`X-CSRF-Token`) on every state-changing
     request. A cross-site form post or <img> tag can trigger the browser
     to *send* the session cookie automatically, but it cannot *read* the
     CSRF cookie's value to put it in a custom header — same-origin
     policy blocks that. That's the whole defense.
  3. The server recomputes the expected signed value from the session id
     + secret and compares it (constant-time) against the header.

This is stronger than a bare double-submit cookie (where an attacker who
can set *any* cookie on your origin — e.g. via a subdomain takeover or a
cookie-setting bug elsewhere — could try to also set the CSRF cookie):
binding the signature to the session id means a forged CSRF cookie value
still has to match the *specific session* the request is trying to ride
along with, which the attacker doesn't know.

Deliberately dependency-free (stdlib only: hmac, hashlib, secrets).
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass

CSRF_COOKIE_NAME = "c123_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

# Methods that don't change state don't need a CSRF check (§19 — this
# only protects state-changing requests).
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class CsrfToken:
    cookie_value: str  # what goes in the (non-HttpOnly) CSRF cookie


def _sign(session_id: str, nonce: str, secret_key: str) -> str:
    mac = hmac.new(secret_key.encode("utf-8"), f"{session_id}:{nonce}".encode("utf-8"), digestmod="sha256")
    return mac.hexdigest()


def issue_csrf_token(session_id: str, secret_key: str) -> CsrfToken:
    nonce = secrets.token_urlsafe(16)
    signature = _sign(session_id, nonce, secret_key)
    return CsrfToken(cookie_value=f"{nonce}.{signature}")


def verify_csrf(*, session_id: str, secret_key: str, cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    # Double-submit: cookie and header must literally match too — this
    # stops an attacker who somehow knows a *stale* valid token for this
    # session but can't read the current cookie from replaying it via the
    # header alone without also controlling the cookie.
    if not hmac.compare_digest(cookie_value, header_value):
        return False
    try:
        nonce, signature = cookie_value.split(".", 1)
    except ValueError:
        return False
    expected = _sign(session_id, nonce, secret_key)
    return hmac.compare_digest(expected, signature)


def requires_csrf_check(method: str) -> bool:
    return method.upper() not in SAFE_METHODS
