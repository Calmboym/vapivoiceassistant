"""
Centralized redaction for logs and audit metadata (Phase 4 spec §24).

Phase 1-3 already had a redaction processor
(app/core/logging.py::_redact_processor) — it's kept, not replaced, but it
had two real gaps, found by actually writing tests against it rather than
just reading it:

  1. It only redacted *top-level* keys of the structlog event dict. A
     nested value like `logger.info("x", user={"password": "hunter2"})`
     sailed straight through, because "user" doesn't match the sensitive
     pattern — only "password" does, and it's one level down.
  2. Its pattern list didn't include "cookie", which §24 explicitly
     requires ("Automatically redact: ... cookie ...").

Both are fixed here, in one place, and this module has zero dependency on
structlog — `_redact_processor` in core/logging.py now just calls
`redact_value()` from here. That split is what makes the redaction *logic*
unit-testable without structlog installed (structlog isn't available in
this sandbox — see tests/test_security_core.py::RedactionTests, which
really runs against this module directly).
"""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|secret|token|api[_-]?key|card[_-]?number|cvv|passport"
    r"|ssn|auth|cookie|iban|account[_-]?number|routing[_-]?number|pin)",
    re.IGNORECASE,
)

REDACTED = "[REDACTED]"

# Belt-and-suspenders for values that leak a secret even under an
# innocuous-looking key (e.g. a log line like `note="retrying with Bearer
# eyJhbGciOi..."`). Deliberately conservative — this only matches strings
# with a recognizable secret *prefix*, so it won't eat ordinary prose.
_SECRET_VALUE_PATTERN = re.compile(
    r"(Bearer\s+[A-Za-z0-9\-_.]{10,}"
    r"|Basic\s+[A-Za-z0-9+/=]{10,}"
    r"|sk_(live|test)_[A-Za-z0-9]{8,}"
    r"|whsec_[A-Za-z0-9]{8,})"
)


def _key_is_sensitive(key: Any) -> bool:
    return isinstance(key, str) and bool(SENSITIVE_KEY_PATTERN.search(key))


def redact_string_value(value: str) -> str:
    return _SECRET_VALUE_PATTERN.sub(REDACTED, value)


def redact_value(data: Any, *, _depth: int = 0) -> Any:
    """Recursively redacts dict keys matching SENSITIVE_KEY_PATTERN
    (values replaced wholesale) and, for plain strings that survive that
    pass, scrubs any embedded secret-looking substrings. Depth-capped so a
    pathological/cyclic structure can't cause unbounded recursion."""
    if _depth > 12:
        return "[TRUNCATED]"
    if isinstance(data, dict):
        return {
            k: (REDACTED if _key_is_sensitive(k) else redact_value(v, _depth=_depth + 1))
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return type(data)(redact_value(v, _depth=_depth + 1) for v in data)
    if isinstance(data, str):
        return redact_string_value(data)
    return data
