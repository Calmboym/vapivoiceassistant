"""
Framework-agnostic security core for Phase 4 (auth/RBAC/security
hardening). Every module in this package imports nothing beyond the
Python standard library, on purpose: it is the one part of Phase 4 that
can be *actually executed* in a sandbox with no network access and none
of fastapi/sqlalchemy/pydantic/argon2-cffi installed (see
docs/PRODUCTION_CHECKLIST.md item 4a), and it is also the highest-value
part to have real, run tests for regardless of environment — it's where
the IDOR/authorization decisions actually get made.

app/api/deps_auth.py, app/models/*, and app/services/* are the
FastAPI/SQLAlchemy-coupled layer built ON TOP of this package. They
translate an HTTP request/DB row into the plain objects these functions
take, and translate the AuthDecision/bool results back into HTTP
responses — they should contain as little *logic* as possible, so that
almost everything worth unit testing already has been, here.
"""
