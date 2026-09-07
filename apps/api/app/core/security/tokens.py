"""
Secure random tokens for sessions, password resets, email verification, and
booking-verification sessions (Phase 4 spec §5, §28, §12).

Deliberately dependency-free (stdlib only: secrets, hashlib, hmac, time) so
it can be imported and unit-tested without FastAPI/SQLAlchemy present.

Design:
  * The token the browser/client holds (cookie value, emailed reset link,
    etc.) is a high-entropy random string — `secrets.token_urlsafe(32)` is
    256 bits of entropy from the OS CSPRNG.
  * The database NEVER stores that raw token (§5: "Never store raw session
    tokens in the database. Only store a cryptographic hash of the
    token."). It stores `hash_token(token)` instead, and a lookup hashes
    the incoming token and does an indexed equality match.
  * Because the token already has 256 bits of entropy, an unsalted SHA-256
    is an acceptable *lookup* hash here (this is not a password — there is
    nothing to brute-force offline; the only way to produce a matching
    hash is to already hold the original 256-bit token). Passwords are
    different and use Argon2id instead — see passwords.py.
  * `verify_token` uses a constant-time comparison so a timing side
    channel can't leak how many hash-prefix bytes matched.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_token(nbytes: int = 32) -> str:
    """A URL-safe, high-entropy random token. 32 bytes = 256 bits."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Deterministic lookup hash for a high-entropy token. See module
    docstring for why plain SHA-256 (no per-token salt) is appropriate
    here specifically, unlike password hashing."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """Constant-time comparison — never use `==` on secret-derived values."""
    return hmac.compare_digest(hash_token(token), token_hash)


def is_expired(expires_at: datetime, *, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now >= expires_at


@dataclass(frozen=True)
class IssuedToken:
    """What a service layer gets back when it mints a new token: the raw
    value (send this to the client / email it — never persist it) and the
    hash (persist this — never send it anywhere)."""

    raw: str
    hash: str
    expires_at: datetime

    @classmethod
    def issue(cls, *, ttl: timedelta, nbytes: int = 32, now: datetime | None = None) -> "IssuedToken":
        raw = generate_token(nbytes)
        return cls(raw=raw, hash=hash_token(raw), expires_at=(now or utcnow()) + ttl)


# --- opaque IDs (call_id, request_id-style correlation IDs, etc.) ---------
# Not secrets — just collision-resistant identifiers. Kept here so every
# ID-looking string in the codebase is generated the same way.


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"
