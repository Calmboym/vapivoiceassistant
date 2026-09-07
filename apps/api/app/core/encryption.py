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
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_DEV_PREFIX = "UNENCRYPTED-DEV:"


def _get_fernet():
    settings = get_settings()
    if not settings.field_encryption_key:
        return None
    from cryptography.fernet import Fernet  # imported lazily; optional dependency in dev/mock mode

    return Fernet(settings.field_encryption_key.encode("utf-8"))


def encrypt_sensitive(plaintext: str) -> str:
    fernet = _get_fernet()
    if fernet is None:
        logger.warning("field_encryption_key_not_set_storing_unencrypted_dev_only")
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
