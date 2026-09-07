"""
Phase 6 Milestone 1: payment domain logic that doesn't need a database.

Deliberately dependency-free (stdlib only — no FastAPI, no Pydantic, no
SQLAlchemy, no `stripe`), same discipline as app/core/security/*.py and
app/core/vapi/*.py. The payment *state machine* (which transitions are
legal, and what each one means for a booking's payment_status) is business
logic, not I/O — it belongs here, testable without a database, per this
codebase's established rule ("if you're tempted to add an `if` that
decides an outcome, it almost certainly belongs in app/core/*, not in a
route or a model").

Modules:
  state_machine.py   PAYMENT_SESSION_STATUSES, the allowed-transition
                      table, and the mapping from a Payment's session
                      status to the (pre-existing, Phase 1-3)
                      Booking.payment_status vocabulary.
"""
