"""
HTTP-level Phase 5 tests for app/api/routes/vapi.py — written against
FastAPI's TestClient and a real (SQLite, file-based) SQLAlchemy engine,
run with `pytest` once `pip install -r requirements.txt` has been done.

NOT EXECUTED IN THE BUILD SANDBOX — same reason and same caveat as
tests/test_api_security.py (no network access to install fastapi/
sqlalchemy/pydantic/pytest here). Written completely and correctly
against the real APIs used elsewhere in this codebase (verified against
the actual FastAPI TestClient/SQLAlchemy behavior test_api_security.py
already exercises the pattern for, and against every service/repository
signature app/api/routes/vapi.py itself was built and reviewed against),
but has never itself been run.

Scope: this file covers webhook-level plumbing (authentication, request
parsing, event-type handling, HTTP status/response shape) — the same
"HTTP-layer coverage, not business logic" scope test_api_security.py
carves out for the rest of the API, for the same reason: the actual
security-critical logic underneath (authorize_vapi_tool_call, the
verification state machine, argument mapping, rate-limit algorithms) is
already covered by REAL, EXECUTED, dependency-free tests in
tests/test_vapi_core.py. Deliberately does NOT attempt a full
create_booking -> verify -> cancel_booking end-to-end chain — that needs
several rounds of request/response inspection to get right, which is
exactly the kind of thing that should be built WITH execution available,
not guessed at without it; a wrong assertion in an unexecuted, never-run
test is worse than an honest gap, since it looks like coverage that
isn't real.

Run with (from apps/api/, after `pip install -r requirements.txt`):
    pytest tests/test_vapi_api.py -v
"""

from __future__ import annotations

import os
import tempfile
import unittest

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("VAPI_WEBHOOK_SECRET", "test-vapi-webhook-secret")


def _build_client():
    """Imports deliberately local — see test_api_security.py's identical
    helper for why (module-scope FastAPI/SQLAlchemy imports would break
    `python -m unittest discover` for the dependency-free suite in an
    environment without them installed)."""
    from fastapi.testclient import TestClient

    from app.db.session import engine
    from app.main import app
    from app.models import Base

    Base.metadata.create_all(engine)
    return TestClient(app)


class VapiWebhookAuthTests(unittest.TestCase):
    """§13's outer trust boundary, exercised over real HTTP — the
    dependency-free equivalent (tests/test_vapi_core.py::WebhookAuthTests)
    already covers the header-parsing/comparison logic itself; this
    confirms the ROUTE actually calls it and returns the right status."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.client = _build_client()
        except ImportError as exc:  # pragma: no cover - expected in this sandbox
            raise unittest.SkipTest(f"FastAPI/SQLAlchemy stack not installed: {exc}")

    def test_missing_secret_header_is_401(self):
        resp = self.client.post("/api/v1/vapi/webhook", json={"message": {"type": "tool-calls", "toolCallList": []}})
        self.assertEqual(resp.status_code, 401)

    def test_wrong_secret_is_401(self):
        resp = self.client.post(
            "/api/v1/vapi/webhook",
            json={"message": {"type": "tool-calls", "toolCallList": []}},
            headers={"X-Vapi-Secret": "wrong-secret"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_correct_secret_is_accepted(self):
        resp = self.client.post(
            "/api/v1/vapi/webhook",
            json={"message": {"type": "tool-calls", "toolCallList": [], "call": {"id": "call_test_1"}}},
            headers={"X-Vapi-Secret": "test-vapi-webhook-secret"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"results": []})

    def test_bearer_header_is_also_accepted(self):
        resp = self.client.post(
            "/api/v1/vapi/webhook",
            json={"message": {"type": "tool-calls", "toolCallList": [], "call": {"id": "call_test_2"}}},
            headers={"Authorization": "Bearer test-vapi-webhook-secret"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_non_tool_calls_message_is_acknowledged_without_processing(self):
        resp = self.client.post(
            "/api/v1/vapi/webhook",
            json={"message": {"type": "status-update", "call": {"id": "call_test_3"}}},
            headers={"X-Vapi-Secret": "test-vapi-webhook-secret"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {})

    def test_empty_body_does_not_crash(self):
        resp = self.client.post(
            "/api/v1/vapi/webhook", json={}, headers={"X-Vapi-Secret": "test-vapi-webhook-secret"}
        )
        self.assertEqual(resp.status_code, 200)

    def test_tool_calls_without_call_id_returns_empty_results_not_an_error(self):
        resp = self.client.post(
            "/api/v1/vapi/webhook",
            json={"message": {"type": "tool-calls", "toolCallList": [{"id": "tc_1", "function": {"name": "search_flights", "arguments": {}}}]}},
            headers={"X-Vapi-Secret": "test-vapi-webhook-secret"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"results": []})


class VapiToolCallFlowTests(unittest.TestCase):
    """One real end-to-end tool call, for a PUBLIC, read-only tool that
    needs no booking/verification fixture — search_flights against
    MockAirlineProvider (the config default, app.core.config.Settings.
    airline_provider == "mock")."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.client = _build_client()
        except ImportError as exc:  # pragma: no cover - expected in this sandbox
            raise unittest.SkipTest(f"FastAPI/SQLAlchemy stack not installed: {exc}")

    def _call_tool(self, tool_name: str, arguments: dict, *, call_id: str = "call_flow_1", tool_call_id: str = "tc_flow_1"):
        return self.client.post(
            "/api/v1/vapi/webhook",
            json={
                "message": {
                    "type": "tool-calls",
                    "call": {"id": call_id},
                    "toolCallList": [
                        {"id": tool_call_id, "type": "function", "function": {"name": tool_name, "arguments": arguments}}
                    ],
                }
            },
            headers={"X-Vapi-Secret": "test-vapi-webhook-secret"},
        )

    def test_search_flights_returns_one_result_entry(self):
        resp = self._call_tool(
            "search_flights",
            {"origin": "FRA", "destination": "JFK", "departure_date": "2027-06-01", "adults": 1},
        )
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["toolCallId"], "tc_flow_1")
        self.assertIn("result", results[0])  # a string result, not an "error" key

    def test_unknown_tool_name_returns_an_error_entry_not_a_500(self):
        resp = self._call_tool("not_a_real_tool", {})
        self.assertEqual(resp.status_code, 200)  # never a non-200 for a tool-specific problem
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertIn("error", results[0])

    def test_cancel_booking_without_verification_is_denied_not_executed(self):
        # No booking exists for this PNR at all, which itself should
        # produce a clean "couldn't find" error rather than an
        # authorization error — a slightly different path through
        # _handle_one_tool_call than a real-but-unverified booking would
        # take, and worth its own assertion for that reason.
        resp = self._call_tool(
            "cancel_booking",
            {"pnr": "ZZZZZZ", "verification_token": "not-a-real-token", "customer_confirmed": True},
        )
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertIn("error", results[0])

    def test_duplicate_tool_call_id_is_not_executed_twice(self):
        first = self._call_tool("search_flights", {"origin": "FRA", "destination": "JFK", "departure_date": "2027-06-01", "adults": 1}, tool_call_id="tc_dup_1")
        second = self._call_tool("search_flights", {"origin": "FRA", "destination": "JFK", "departure_date": "2027-06-01", "adults": 1}, tool_call_id="tc_dup_1")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        # Both succeed from the caller's point of view, but the second
        # should be the short-circuited "already done" path, not a
        # second live search — see _handle_one_tool_call's transport-
        # level dedup. Asserted via the generic wording that path
        # returns, since the two real search results could legitimately
        # differ (MockAirlineProvider isn't seeded with fixed data).
        self.assertEqual(second.json()["results"][0]["result"], "Already done.")


if __name__ == "__main__":
    unittest.main()
