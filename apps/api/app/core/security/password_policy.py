"""
Password strength policy (Phase 4 spec §4).

This is *policy* (is this string acceptable as a new password), separate
from *hashing* (passwords.py). Kept separate on purpose: policy is pure
string logic with no crypto dependency at all, so it's trivially testable,
and it's the layer most likely to need tuning (length minimums, blocklist
entries) without touching anything crypto-related.

Deliberately dependency-free (stdlib only).
"""

from __future__ import annotations

from dataclasses import dataclass, field

MIN_LENGTH = 12
MAX_LENGTH = 256  # Argon2id has no problem with long inputs, but an
# unbounded password is a cheap DoS vector (hashing cost scales with
# input processing) — 256 chars is generous for any real passphrase.

# A short, illustrative blocklist of the most common breached/default
# passwords. This is NOT a substitute for a real breached-password corpus
# check (e.g. an offline k-anonymity HaveIBeenPwned range query) — that's
# a good production follow-up noted in docs/SECURITY.md — but it catches
# the most egregious cases for free, offline, with zero dependencies.
_COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "123456", "12345678",
        "123456789", "qwerty", "qwerty123", "letmein", "welcome",
        "welcome123", "admin", "administrator", "iloveyou", "monkey",
        "dragon", "football", "baseball", "trustno1", "sunshine",
        "princess", "abc123", "abcd1234", "changeme", "charter123",
        "airplane123", "passw0rd", "p@ssw0rd", "000000", "11111111",
    }
)


@dataclass(frozen=True)
class PasswordPolicyResult:
    valid: bool
    problems: list[str] = field(default_factory=list)


def validate_password_strength(
    password: str,
    *,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> PasswordPolicyResult:
    problems: list[str] = []

    if len(password) < MIN_LENGTH:
        problems.append(f"Password must be at least {MIN_LENGTH} characters long.")
    if len(password) > MAX_LENGTH:
        problems.append(f"Password must be at most {MAX_LENGTH} characters long.")

    lowered = password.lower()

    if lowered in _COMMON_PASSWORDS:
        problems.append("This password is far too common. Choose something less guessable.")

    if len(set(password)) <= 3 and len(password) >= MIN_LENGTH:
        # e.g. "aaaaaaaaaaaa", "abababababab"
        problems.append("Password has too little variety in its characters.")

    if _is_sequential_run(lowered):
        problems.append("Password looks like a simple keyboard/number sequence.")

    # Check the email's local part (before "@"), not the raw address —
    # "janedoe12345secure" should be rejected for janedoe@example.com
    # even though it doesn't contain the literal "@example.com" suffix,
    # which comparing the raw email string would have required. Found by
    # test_contains_email_rejected actually failing, not by inspection.
    email_local_part = email.split("@", 1)[0] if email and "@" in email else email
    for label, value in (("email", email_local_part), ("first name", first_name), ("last name", last_name)):
        if value and len(value) >= 3 and value.lower() in lowered:
            problems.append(f"Password must not contain your {label}.")

    return PasswordPolicyResult(valid=not problems, problems=problems)


def _is_sequential_run(lowered: str, run_length: int = 6) -> bool:
    """Catches things like 'abcdefgh' or '12345678' — a straight ascending
    (or descending) run of `run_length`+ consecutive code points."""
    if len(lowered) < run_length:
        return False
    ascending = descending = 1
    best = 1
    for i in range(1, len(lowered)):
        prev, curr = ord(lowered[i - 1]), ord(lowered[i])
        if curr == prev + 1:
            ascending += 1
            descending = 1
        elif curr == prev - 1:
            descending += 1
            ascending = 1
        else:
            ascending = descending = 1
        best = max(best, ascending, descending)
        if best >= run_length:
            return True
    return False
