"""
Field-level encryption for data that must be encrypted at rest — currently
just passport numbers (§10: "encrypt sensitive fields at rest").

Requires the `cryptography` package and a FIELD_ENCRYPTION_KEY (a
Fernet key — generate one with `Fernet.generate_key()` and store it in a
secrets manager, never in source control).

Development fallback: if no key is configured, values are stored with a
"UNENCRYPTED-DEV:" prefix and a loud warning is logged on every use. This
path is intentionally awkward to keep it out of production — the settings
model refuses to boot with APP_ENV=production unless FIELD_ENCRYPTION_KEY
is set (see app/core/config.py).

T-7 (WBS-6.2, docs/TASK_BOARD.md) finding: `get_settings`/`get_logger`
used to be imported at MODULE level here, even though `mask_for_speech`
below — the one function §10's "never read a full passport number aloud"
rule actually depends on — touches neither settings nor logging. That
meant the mere act of importing this module required pydantic AND
structlog to be installed, so `mask_for_speech` could never be exercised
by the dependency-free test tier (the sandbox this project has run every
session in has neither package) — the exact tier this file's own
docstring, and MASTER_RULES.md's "dependency-free test isolation"
principle, says safety-critical logic belongs in. Both imports are now
lazy (moved inside the functions that actually need them, same pattern
`_get_fernet` already used for `cryptography.fernet`), so `mask_for_speech`
importing and running requires nothing beyond the stdlib. `encrypt_
sensitive`/`decrypt_sensitive`'s behavior is unchanged either way — they
still call `get_settings()`/log the same warning, just resolved at call
time instead of import time. See tests/test_voice_conversation_core.py's
`PassportNeverReadAloudTests` for the test this fix unblocks.
"""

from __future__ import annotations

_DEV_PREFIX = "UNENCRYPTED-DEV:"


def _get_fernet():
    from app.core.config import get_settings  # lazy — see module docstring (T-7)

    settings = get_settings()
    if not settings.field_encryption_key:
        return None
    from cryptography.fernet import Fernet  # imported lazily; optional dependency in dev/mock mode

    return Fernet(settings.field_encryption_key.encode("utf-8"))


def encrypt_sensitive(plaintext: str) -> str:
    fernet = _get_fernet()
    if fernet is None:
        from app.core.logging import get_logger  # lazy — see module docstring (T-7)

        get_logger(__name__).warning("field_encryption_key_not_set_storing_unencrypted_dev_only")
        return _DEV_PREFIX + plaintext
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_sensitive(ciphertext: str) -> str:
    if ciphertext.startswith(_DEV_PREFIX):
        return ciphertext[len(_DEV_PREFIX):]
    fernet = _get_fernet()
    if fernet is None:
        raise RuntimeError("FIELD_ENCRYPTION_KEY is not set — cannot decrypt stored value")
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def mask_for_speech(passport_number: str) -> str:
    """Never read a full passport number aloud (§10). Use this for anything
    a Vapi tool response might cause the agent to repeat back."""
    if len(passport_number) <= 4:
        return "***"
    return "*" * (len(passport_number) - 4) + passport_number[-4:]
