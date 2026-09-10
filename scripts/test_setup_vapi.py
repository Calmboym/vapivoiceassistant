"""
Dependency-free tests for scripts/setup_vapi.py's pure logic (payload
construction, the suggested-system-prompt loader, and create-vs-update
planning). Deliberately does NOT import httpx or exercise VapiClient —
that half of setup_vapi.py needs a real network + real credentials and is
Written/reviewed/not executed, same as every other real-integration file
in this project (see setup_vapi.py's own module docstring).

Run directly (stdlib unittest only, no pytest needed, matches
tests/test_core_logic.py's own "python3 -m unittest" convention):

    cd scripts && python3 -m unittest test_setup_vapi -v

or, from the repo root:

    python3 -m unittest discover -s scripts -p "test_setup_vapi.py" -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import setup_vapi  # noqa: E402
from app.core.vapi.tool_schemas import VAPI_TOOL_SCHEMAS  # noqa: E402


class LoadSuggestedSystemPromptTests(unittest.TestCase):
    def test_loads_real_docs_vapi_md_without_error(self) -> None:
        prompt = setup_vapi.load_suggested_system_prompt()
        self.assertIn("Charter123's voice booking assistant", prompt)
        self.assertIn("verify_booking_customer", prompt)
        self.assertIn("transfer_to_human", prompt)

    def test_raises_clearly_on_missing_heading(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("# Some other doc\n\nNo suggested prompt heading here.\n")
            path = Path(f.name)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                setup_vapi.load_suggested_system_prompt(path)
            self.assertIn("Suggested system prompt", str(ctx.exception))
        finally:
            path.unlink()

    def test_raises_clearly_on_unterminated_fence(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("## Suggested system prompt\n\n```\nunterminated")
            path = Path(f.name)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                setup_vapi.load_suggested_system_prompt(path)
            self.assertIn("unterminated", str(ctx.exception).lower())
        finally:
            path.unlink()


class BuildServerConfigTests(unittest.TestCase):
    def test_prefers_credential_id_over_secret(self) -> None:
        server = setup_vapi.build_server_config(
            "https://example.com/webhook", secret="s3cr3t", credential_id="cred_abc"
        )
        self.assertEqual(server, {"url": "https://example.com/webhook", "credentialId": "cred_abc"})

    def test_falls_back_to_secret(self) -> None:
        server = setup_vapi.build_server_config(
            "https://example.com/webhook", secret="s3cr3t", credential_id=None
        )
        self.assertEqual(server, {"url": "https://example.com/webhook", "secret": "s3cr3t"})

    def test_raises_if_neither_secret_nor_credential(self) -> None:
        with self.assertRaises(ValueError):
            setup_vapi.build_server_config("https://example.com/webhook", secret=None, credential_id=None)

    def test_raises_without_server_url(self) -> None:
        with self.assertRaises(ValueError):
            setup_vapi.build_server_config("", secret="s3cr3t", credential_id=None)


class BuildFunctionToolPayloadTests(unittest.TestCase):
    def test_shape_matches_vapi_create_tool_contract(self) -> None:
        schema = VAPI_TOOL_SCHEMAS["cancel_booking"]
        server = {"url": "https://example.com/webhook", "secret": "s"}
        payload = setup_vapi.build_function_tool_payload(schema, server)
        self.assertEqual(payload["type"], "function")
        self.assertEqual(payload["function"]["name"], "cancel_booking")
        self.assertEqual(payload["function"]["description"], schema.description)
        self.assertEqual(payload["function"]["parameters"], dict(schema.parameters))
        self.assertEqual(payload["server"], server)

    def test_every_registered_schema_builds_a_valid_payload(self) -> None:
        server = {"url": "https://example.com/webhook", "secret": "s"}
        for name, schema in VAPI_TOOL_SCHEMAS.items():
            payload = setup_vapi.build_function_tool_payload(schema, server)
            self.assertEqual(payload["function"]["name"], name)
            self.assertEqual(payload["function"]["parameters"]["type"], "object")


class BuildTransferCallToolPayloadTests(unittest.TestCase):
    def test_shape(self) -> None:
        payload = setup_vapi.build_transfer_call_tool_payload("+15551234567", "hold please")
        self.assertEqual(payload["type"], "transferCall")
        self.assertEqual(len(payload["destinations"]), 1)
        dest = payload["destinations"][0]
        self.assertEqual(dest, {"type": "number", "number": "+15551234567", "message": "hold please"})

    def test_raises_without_destination(self) -> None:
        with self.assertRaises(ValueError):
            setup_vapi.build_transfer_call_tool_payload("", "hold please")


class BuildAssistantPayloadTests(unittest.TestCase):
    def test_shape(self) -> None:
        server = {"url": "https://example.com/webhook", "secret": "s"}
        payload = setup_vapi.build_assistant_payload(
            name="Test Assistant",
            server=server,
            tool_ids=["id1", "id2"],
            model_provider="openai",
            model_name="gpt-4o",
            system_prompt="be helpful",
        )
        self.assertEqual(payload["name"], "Test Assistant")
        self.assertEqual(payload["server"], server)
        self.assertEqual(payload["model"]["provider"], "openai")
        self.assertEqual(payload["model"]["model"], "gpt-4o")
        self.assertEqual(payload["model"]["toolIds"], ["id1", "id2"])
        self.assertEqual(payload["model"]["messages"], [{"role": "system", "content": "be helpful"}])


class PlanFunctionToolUpsertsTests(unittest.TestCase):
    def test_all_creates_when_nothing_exists(self) -> None:
        server = {"url": "https://example.com/webhook", "secret": "s"}
        plan = setup_vapi.plan_function_tool_upserts(VAPI_TOOL_SCHEMAS, server, {})
        self.assertEqual(len(plan), len(VAPI_TOOL_SCHEMAS))
        self.assertTrue(all(e["action"] == "create" and e["existing_id"] is None for e in plan))

    def test_matches_existing_by_name_for_update(self) -> None:
        server = {"url": "https://example.com/webhook", "secret": "s"}
        existing = {"cancel_booking": "tool_existing_123"}
        plan = setup_vapi.plan_function_tool_upserts(VAPI_TOOL_SCHEMAS, server, existing)
        by_name = {e["name"]: e for e in plan}
        self.assertEqual(by_name["cancel_booking"]["action"], "update")
        self.assertEqual(by_name["cancel_booking"]["existing_id"], "tool_existing_123")
        # Everything else with no match is still a create.
        other = by_name["search_flights"]
        self.assertEqual(other["action"], "create")
        self.assertIsNone(other["existing_id"])

    def test_plan_covers_exactly_the_21_registered_tools(self) -> None:
        server = {"url": "https://example.com/webhook", "secret": "s"}
        plan = setup_vapi.plan_function_tool_upserts(VAPI_TOOL_SCHEMAS, server, {})
        planned_names = {e["name"] for e in plan}
        self.assertEqual(planned_names, set(VAPI_TOOL_SCHEMAS.keys()))
        self.assertEqual(len(VAPI_TOOL_SCHEMAS), 21)


class PlanTransferCallUpsertTests(unittest.TestCase):
    def test_none_when_no_destination_number(self) -> None:
        plan = setup_vapi.plan_transfer_call_upsert(None, "msg", [])
        self.assertIsNone(plan)
        plan = setup_vapi.plan_transfer_call_upsert("", "msg", [])
        self.assertIsNone(plan)

    def test_create_when_none_exist(self) -> None:
        plan = setup_vapi.plan_transfer_call_upsert("+15551234567", "msg", [])
        self.assertEqual(plan["action"], "create")
        self.assertIsNone(plan["existing_id"])

    def test_update_when_exactly_one_exists(self) -> None:
        plan = setup_vapi.plan_transfer_call_upsert("+15551234567", "msg", ["tool_xyz"])
        self.assertEqual(plan["action"], "update")
        self.assertEqual(plan["existing_id"], "tool_xyz")

    def test_refuses_to_guess_when_multiple_exist(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            setup_vapi.plan_transfer_call_upsert("+15551234567", "msg", ["a", "b"])
        self.assertIn("refusing to guess", str(ctx.exception).lower())


class IndexExistingToolsTests(unittest.TestCase):
    def test_splits_function_and_transfer_tools(self) -> None:
        existing = [
            {"id": "t1", "type": "function", "function": {"name": "cancel_booking"}},
            {"id": "t2", "type": "function", "function": {"name": "search_flights"}},
            {"id": "t3", "type": "transferCall"},
            {"id": "t4", "type": "apiRequest"},  # some unrelated tool type — must be ignored
        ]
        by_name, transfer_ids = setup_vapi._index_existing_tools(existing)
        self.assertEqual(by_name, {"cancel_booking": "t1", "search_flights": "t2"})
        self.assertEqual(transfer_ids, ["t3"])

    def test_empty_input(self) -> None:
        by_name, transfer_ids = setup_vapi._index_existing_tools([])
        self.assertEqual(by_name, {})
        self.assertEqual(transfer_ids, [])


class ArgParserTests(unittest.TestCase):
    def test_model_provider_and_name_are_required(self) -> None:
        parser = setup_vapi._build_arg_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])  # missing --model-provider/--model-name

    def test_apply_defaults_to_false(self) -> None:
        parser = setup_vapi._build_arg_parser()
        args = parser.parse_args(["--model-provider", "openai", "--model-name", "gpt-4o"])
        self.assertFalse(args.apply)


class MainDryRunTests(unittest.TestCase):
    """main() with no --apply must succeed with stdlib only — no httpx,
    no network, no real Vapi credentials. This is the one place this test
    file actually calls main(), and only ever in dry-run mode."""

    def test_dry_run_exits_zero_without_network_or_credentials(self) -> None:
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = setup_vapi.main(["--model-provider", "openai", "--model-name", "gpt-4o"])
        self.assertEqual(exit_code, 0)
        output = buf.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("dry run. Nothing was sent.", output)


if __name__ == "__main__":
    unittest.main()
