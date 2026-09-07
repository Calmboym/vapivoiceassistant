"""
Argon2id password hashing (Phase 4 spec §4: "Use Argon2id... do not invent
a custom password hashing algorithm... use a standard password hashing
implementation appropriate for Python").

This uses `cryptography.hazmat.primitives.kdf.argon2.Argon2id` — the
`cryptography` package (pyca/cryptography, already a dependency of this
project for Fernet field encryption — see app/core/encryption.py) added a
native Argon2id KDF binding to OpenSSL/Rust's audited implementation.
That means Argon2id password hashing does NOT need the separate
`argon2-cffi` package this project's requirements.txt currently lists —
`cryptography` alone is sufficient. This was confirmed by actually
importing and round-tripping it in this sandbox (`cryptography==46.0.6`),
not assumed — see tests/test_security_core.py::PasswordHasherTests, which
really runs.

Default parameters follow OWASP's Password Storage Cheat Sheet current
minimum-configuration recommendation for Argon2id: memory=19 MiB (19456
KiB), iterations=2, parallelism=1
(https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html,
checked at the time this was written). A higher-resource deployment can
raise these — see `needs_rehash` below, which is exactly the mechanism
for migrating everyone's hash forward the next time each of them logs in,
without a mass password reset.

Encoded format (stored in `users.password_hash`):
    argon2id$<memory_cost_kib>$<iterations>$<lanes>$<salt_b64>$<hash_b64>
This is a compact, self-describing format (deliberately not the official
PHC string format, to avoid re-implementing PHC parsing by hand) so a
future parameter change doesn't invalidate already-stored hashes — the
params travel with the hash.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

_ALGO_TAG = "argon2id"


@dataclass(frozen=True)
class Argon2Parameters:
    memory_cost_kib: int  # "m" — KiB of memory
    iterations: int  # "t"
    lanes: int  # "p" — degree of parallelism
    hash_len: int = 32
    salt_len: int = 16


# OWASP Password Storage Cheat Sheet minimum configuration for Argon2id.
DEFAULT_PARAMETERS = Argon2Parameters(memory_cost_kib=19 * 1024, iterations=2, lanes=1)


class PasswordHasher:
    """Never invent your own scheme here — this is a thin, explicit wrapper
    around a single audited primitive. §4 forbids a custom algorithm; this
    class exists so callers never touch Argon2id directly and can't get a
    parameter wrong."""

    def __init__(self, parameters: Argon2Parameters = DEFAULT_PARAMETERS):
        self.parameters = parameters

    def hash(self, password: str) -> str:
        if not isinstance(password, str) or password == "":
            raise ValueError("password must be a non-empty string")
        p = self.parameters
        salt = os.urandom(p.salt_len)
        kdf = Argon2id(salt=salt, length=p.hash_len, iterations=p.iterations, lanes=p.lanes, memory_cost=p.memory_cost_kib)
        derived = kdf.derive(password.encode("utf-8"))
        return self._encode(p, salt, derived)

    def verify(self, password: str, encoded_hash: str) -> bool:
        """Never raises — a malformed stored hash or a wrong password both
        just mean 'not authenticated'. Callers must not distinguish the
        two in any response (§28: don't reveal which part was wrong)."""
        try:
            params, salt, expected = self._decode(encoded_hash)
        except (ValueError, IndexError):
            return False
        try:
            kdf = Argon2id(
                salt=salt, length=params.hash_len, iterations=params.iterations,
                lanes=params.lanes, memory_cost=params.memory_cost_kib,
            )
            kdf.verify(password.encode("utf-8"), expected)
            return True
        except InvalidKey:
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        """True if `encoded_hash` was produced with different parameters
        than this instance's current `self.parameters` — the caller
        should re-hash the (already-verified-correct) password and update
        the stored value. This is how you roll out a stronger cost factor
        over time without forcing every user to reset their password."""
        try:
            params, _salt, _hash = self._decode(encoded_hash)
        except (ValueError, IndexError):
            return True
        return params != self.parameters

    @staticmethod
    def _encode(params: Argon2Parameters, salt: bytes, derived: bytes) -> str:
        salt_b64 = base64.b64encode(salt).decode("ascii")
        hash_b64 = base64.b64encode(derived).decode("ascii")
        return f"{_ALGO_TAG}${params.memory_cost_kib}${params.iterations}${params.lanes}${salt_b64}${hash_b64}"

    @staticmethod
    def _decode(encoded: str) -> tuple[Argon2Parameters, bytes, bytes]:
        parts = encoded.split("$")
        if len(parts) != 6 or parts[0] != _ALGO_TAG:
            raise ValueError("unrecognized password hash format")
        _, memory_cost_kib, iterations, lanes, salt_b64, hash_b64 = parts
        salt = base64.b64decode(salt_b64)
        derived = base64.b64decode(hash_b64)
        params = Argon2Parameters(
            memory_cost_kib=int(memory_cost_kib), iterations=int(iterations),
            lanes=int(lanes), hash_len=len(derived), salt_len=len(salt),
        )
        return params, salt, derived


# Module-level singleton for convenience — services should still be able
# to inject a PasswordHasher(custom_parameters) for tests that want cheap
# parameters, so this is a default, not a hidden global requirement.
default_password_hasher = PasswordHasher()
