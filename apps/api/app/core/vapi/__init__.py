"""
Phase 5: Vapi integration glue.

Everything in this package is deliberately dependency-free (stdlib only —
no FastAPI, no Pydantic, no SQLAlchemy) so it can be imported and unit
tested in this sandbox without any of them installed, the same discipline
app/core/security/*.py already follows. It is "glue," not authorization
policy — the actual allow/deny decision for a tool call still lives in
app/core/security/vapi_authorization.py::authorize_vapi_tool_call(),
which this package's callers (app/api/routes/vapi.py) invoke exactly as
prescribed in PROJECT_HANDOFF_PHASE_4.md §10.

Modules:
  tool_schemas.py       The JSON-schema + UX metadata for every Vapi tool
                         (what the LLM sees, what it means, whether it
                         mutates, whether it needs a confirmation). Kept
                         separate from TOOL_AUTHORIZATION_MATRIX on
                         purpose — that file is pure authorization policy;
                         this is tool *shape*. A real test asserts the two
                         stay in sync (tests/test_vapi_core.py).
  argument_mapping.py    Pure functions: a Vapi tool call's already-parsed
                         `arguments` dict in, a plain dict of kwargs a
                         route handler can feed to the existing
                         Pydantic request schemas out. Also owns
                         server-side idempotency-key derivation (reusing
                         app/core/idempotency.py::derive_idempotency_key)
                         so an idempotency key is never trusted verbatim
                         from the LLM's own output.
"""
