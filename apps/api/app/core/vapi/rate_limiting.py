"""
Vapi rate-limit keying policy (Phase 5.2).

The actual algorithms (FixedWindowRateLimiter, BackoffLockout) and their
RATE_LIMIT_PROFILES (including "vapi_webhook" and "vapi_tool", already
defined in Phase 4) live in app/core/security/rate_limiter.py and are
already tested there, independent of any of this — see
tests/test_security_core.py. This module adds ONLY the Vapi-specific
question those generic, reusable pieces don't answer on their own: what
key does each profile get checked against. Kept dependency-free (no
Redis, no FastAPI) so the keying policy itself is testable without either
— see tests/test_vapi_core.py::RateLimitKeyingTests.
"""

from __future__ import annotations

from typing import Optional


def webhook_rate_limit_key(source_ip: Optional[str]) -> str:
    """Keys the "vapi_webhook" profile by source IP. This endpoint's
    caller identity is Vapi's infrastructure as a whole, not an
    individual customer — there is no customer identity yet at the
    webhook-request level, and even once one exists later in a call, a
    client-supplied identity is never a trust boundary in this codebase
    (docs/SECURITY.md §1). IP is the right coarse-grained signal for
    "is this endpoint being hammered," which is the actual threat this
    profile defends against (a misconfigured or compromised integration,
    or a sender that doesn't even hold the webhook secret making enough
    noise to matter before verify_webhook_request() rejects each one).

    Falls back to a single shared bucket if the IP genuinely isn't
    available (e.g. a proxy that doesn't set it) — this fallback can
    only ever make the limit MORE conservative (all such requests share
    one bucket instead of being split by IP), never less, so it isn't a
    bypass, just a coarser one."""
    return f"vapi_webhook:{source_ip}" if source_ip else "vapi_webhook:unknown"


def tool_rate_limit_key(call_id: str) -> str:
    """Keys the "vapi_tool" profile by Vapi's own call_id — deliberately
    not by any customer/user identity: there usually isn't one yet at
    this point in a call, and a client-supplied identity is never a
    trust boundary here regardless (docs/SECURITY.md §1). call_id is not
    attacker-controlled in the sense that matters: this function is only
    ever reached after verify_webhook_request() has already confirmed
    the whole request carries Vapi's shared secret, so an attacker
    without that secret cannot get an arbitrary call_id used as a key at
    all — they cannot reach this function in the first place."""
    return f"vapi_tool:{call_id}"
