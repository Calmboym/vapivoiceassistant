"""
Structured logging via structlog. Every log line is JSON with a bound
request_id/call_id/tool_execution_id where applicable (§31).

REDACTION: `_redact_processor` walks every event dict and masks any key
that looks sensitive before it's ever serialized — this is a safety net,
not a substitute for not logging sensitive data in the first place. Never
pass raw passport numbers, card data, or full auth tokens into a log call
even though this exists.

Phase 4: the actual redaction logic now lives in
app.core.security.redaction (pure, dependency-free, real unit tests in
tests/test_security_core.py::RedactionTests) rather than being
reimplemented here — this file's own pattern used to be a smaller subset
covering only TOP-LEVEL keys; the shared version also recurses into
nested dicts/lists (e.g. a call's metadata blob containing a
`{"payment": {"token": "..."}}` shape) and covers a superset of keys
(cookie, session, stripe/vapi secrets, ...) that §24 explicitly calls
out. One canonical "what counts as sensitive" list, not two that can
silently drift apart.
"""

from __future__ import annotations

import logging
from typing import Any

import structlog

from app.core.security.redaction import redact_value


def _redact_processor(logger: Any, method_name: str, event_dict: dict) -> dict:
    return redact_value(event_dict)


def configure_logging(log_level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=log_level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level.upper(), logging.INFO)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "charter123") -> structlog.BoundLogger:
    return structlog.get_logger(name)
