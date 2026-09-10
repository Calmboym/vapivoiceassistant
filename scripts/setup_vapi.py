#!/usr/bin/env python3
"""
scripts/setup_vapi.py — create/update the 21 registered Vapi tools, the
native transferCall tool, and the Assistant on a real Vapi account, and
(optionally) attach a phone number. Original spec §51. Authorized as
docs/TASK_BOARD.md T-4 / docs/WORK_BREAKDOWN_STRUCTURE.md WBS-2.1.

THIS FILE HAS NEVER BEEN EXECUTED AGAINST A REAL VAPI ACCOUNT. It was
written in a sandbox with no network egress (`403 host_not_allowed` on
every outbound host, confirmed again this session — same class of
blocker documented for T-1 in docs/TASK_BOARD.md) and no `VAPI_API_KEY`.
Its pure, non-networked logic (payload construction, the suggested-
system-prompt loader, create-vs-update planning) IS executed and tested
in this sandbox — see scripts/test_setup_vapi.py and this session's
handoff notes for the exact command and result. The parts that actually
call https://api.vapi.ai are Written, reviewed, cross-checked against
Vapi's current documentation — NOT executed. Do not represent this
script as "tested" beyond that split.

--- What this script does, and in what order ---

  1. Upsert (create-or-update, matched by function name) a `function`-
     type Tool on Vapi for every entry in app.core.vapi.tool_schemas.
     VAPI_TOOL_SCHEMAS (21 tools — the exact set docs/VAPI.md's table
     and tests/test_vapi_core.py::ToolRegistryConsistencyTests already
     pin; this script is deliberately not the place that decides what
     the tool list is, it only pushes whatever that module currently
     defines).
  2. Upsert a native `transferCall`-type Tool (NOT the same thing as the
     `transfer_to_human` function tool from step 1 — see docs/VAPI.md's
     "Transfer to human" section for why these are two separate tools).
     Only attempted if a destination number is supplied.
  3. Upsert the Assistant itself: name, top-level `server` (URL + shared
     secret or credential reference), and `model.toolIds` covering every
     tool from steps 1-2, plus `model.messages` seeded from docs/VAPI.md's
     own "Suggested system prompt" section (read from that file at
     runtime, not duplicated here — see load_suggested_system_prompt()).
  4. If a phone number ID is supplied, PATCH that phone number's
     `assistantId` to point at the assistant from step 3.

Every step is idempotent: re-running this script against the same
account with the same VAPI_ASSISTANT_ID/tool names updates existing
resources in place rather than creating duplicates — same discipline as
app/db/seed.py.

--- Vapi API surface this script depends on ---

All of the following were fetched and read from docs.vapi.ai during this
session (not assumed from training data — training data predates Vapi's
current Custom Credentials system entirely):

  - `POST /tool` / `GET /tool` / `PATCH /tool/{id}`
    (docs.vapi.ai/api-reference/tools/create,
     docs.vapi.ai/tools/custom-tools — function-tool request shape:
     {"type": "function", "function": {name, description, parameters},
      "server": {...}})
  - transferCall tool shape: {"type": "transferCall", "destinations":
    [{"type": "number", "number": ..., "message": ...}]}
    (docs.vapi.ai/call_forwarding, docs.vapi.ai/tools/transfer-call)
  - `POST /assistant` / `PATCH /assistant/{id}`: top-level `server`
    ({url, secret} or {url, credentialId}), `model.provider`/
    `model.model`/`model.toolIds`/`model.messages`
    (docs.vapi.ai/tools/custom-tools "Adding Tools to Assistants via
     API", docs.vapi.ai/server-url/server-authentication)
  - `PATCH /phone-number/{id}`: {"assistantId": "..."}
    (community-confirmed against Vapi's own "Update Phone Number" API
     reference page — see this session's handoff for the exact source)
  - Webhook auth: THIS SESSION CONFIRMED Vapi has moved to a
    dashboard-managed "Custom Credentials" system as the *documented*
    current mechanism, with the older inline `server.secret` field kept
    working under an explicit "Migration from Inline Authentication"
    compatibility note (docs.vapi.ai/server-url/server-authentication).
    This matches — does not contradict — what
    app/core/security/vapi_webhook_auth.py's own docstring already
    independently recorded ("verified ... September 2026"). No public
    API endpoint for *creating* a Custom Credential was found in Vapi's
    API reference sidebar (Credentials is not one of its listed
    resources) — every source describing credential creation describes
    the dashboard only. This script therefore defaults to the inline
    `server.secret` field (VAPI_WEBHOOK_SECRET, already read by the
    running app) and accepts an optional VAPI_WEBHOOK_CREDENTIAL_ID for
    anyone who has created a Custom Credential by hand in the dashboard
    and wants the script to reference it instead. If Vapi's dashboard
    ever exposes credential creation over the API, this is the function
    to extend (build_server_config()) — don't guess at an endpoint shape
    that hasn't been confirmed.

--- What this script deliberately does NOT do ---

Per docs/TASK_BOARD.md T-4's scope note ("any change to existing tool
logic" is out of scope): this script never touches
app/core/vapi/tool_schemas.py, app/core/security/vapi_authorization.py,
or app/api/routes/vapi.py. It only pushes what those files already
define to a live Vapi account. It does not choose an LLM provider/model
for you — docs/VAPI.md is explicit that this integration is
"provider-agnostic by design," so --model-provider/--model-name are
required arguments here, not defaulted, to avoid this script quietly
making that product decision on your behalf.

--- Usage ---

    cd apps/api  # or anywhere — this script locates the repo root itself
    python3 ../scripts/setup_vapi.py --model-provider openai --model-name gpt-4o
        # prints the full plan (every payload this run would send) and exits
        # WITHOUT calling the network. Read this before ever passing --apply.

    python3 ../scripts/setup_vapi.py --model-provider openai --model-name gpt-4o \\
        --transfer-number "+15551234567" --apply
        # actually calls the Vapi API. Requires httpx installed and
        # VAPI_API_KEY/VAPI_SERVER_URL set. Requires explicit --apply,
        # mirroring the customer_confirmed/confirmed pattern MASTER_RULES
        # §3 uses everywhere else a mutation has real consequences —
        # this one has consequences on a live external account instead of
        # in Charter123's own database, but the principle is the same.

Required environment variables (via app.core.config.get_settings(),
same variables the running app already reads):
    VAPI_API_KEY            — server-side management API key (never expose
                               to a browser — see .env.example)
    VAPI_WEBHOOK_SECRET      — shared secret Vapi will send back on every
                               webhook call (or set VAPI_WEBHOOK_CREDENTIAL_ID
                               instead — see above)

Optional, also via get_settings():
    VAPI_ASSISTANT_ID       — update this assistant instead of creating a
                               new one. STRONGLY recommended after the
                               first successful --apply run — see the
                               printed reminder when a new assistant is
                               created.
    VAPI_PHONE_NUMBER_ID    — attach the assistant to this number

New, script-only environment variables (read directly from os.environ,
not added to app.core.config.Settings — the running FastAPI app has no
use for them, only this script does):
    VAPI_SERVER_URL          — REQUIRED for --apply. The full webhook URL,
                               e.g. https://your-domain.com/api/v1/vapi/webhook
    VAPI_WEBHOOK_CREDENTIAL_ID — optional, see above
    VAPI_TRANSFER_NUMBER      — optional; also settable via --transfer-number
    VAPI_TRANSFER_MESSAGE     — optional; also settable via --transfer-message
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

# --- bootstrap: make `app.*` importable no matter what directory this is
# run from (this script lives in scripts/, one level below the repo root;
# the app package lives in apps/api/app) --------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_ROOT = _REPO_ROOT / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.core.vapi.tool_schemas import VAPI_TOOL_SCHEMAS, VapiToolSchema  # noqa: E402
# Deliberately NOT `from app.core.config import get_settings`: Settings is a
# pydantic model, and pydantic is not importable in the sandbox this was
# written in (same T-1 blocker as fastapi/sqlalchemy/httpx — confirmed this
# session: `python3 -c "import pydantic"` raises ModuleNotFoundError here).
# Routing this script's env-var reads through get_settings() would have
# made even the dependency-free dry-run path fail to import, defeating the
# whole point of keeping the pure-logic half of this file free of every
# external dependency. This script reads the same environment variable
# NAMES app.core.config.Settings defines (VAPI_API_KEY, VAPI_WEBHOOK_SECRET,
# VAPI_ASSISTANT_ID, VAPI_PHONE_NUMBER_ID) directly via os.environ instead —
# see _load_env() below. If Settings' aliases for these ever change, update
# _load_env() to match; nothing here re-derives them from Settings.

VAPI_API_BASE = "https://api.vapi.ai"
_VAPI_MD_PATH = _REPO_ROOT / "docs" / "VAPI.md"
_DEFAULT_TRANSFER_MESSAGE = (
    "I'm connecting you with a member of our team now. Please stay on the line."
)


# ===========================================================================
# Pure, dependency-free logic — no network, no httpx import. Exercised by
# scripts/test_setup_vapi.py in this exact sandbox; see that file's own
# header for the command used to run it.
# ===========================================================================


def load_suggested_system_prompt(vapi_md_path: Path = _VAPI_MD_PATH) -> str:
    """Extract the fenced code block under docs/VAPI.md's own "## Suggested
    system prompt" heading, so this script and that doc can never silently
    drift from each other the way docs/PROJECT_ROADMAP.md §6.2 found other
    documentation had — docs/VAPI.md stays the one place this text lives,
    this function only reads it."""
    text = vapi_md_path.read_text(encoding="utf-8")
    marker = "## Suggested system prompt"
    idx = text.find(marker)
    if idx == -1:
        raise RuntimeError(f"{vapi_md_path}: could not find {marker!r} heading")
    after = text[idx:]
    fence_start = after.find("```")
    if fence_start == -1:
        raise RuntimeError(f"{vapi_md_path}: no fenced code block found after {marker!r}")
    fence_start += 3
    fence_end = after.find("```", fence_start)
    if fence_end == -1:
        raise RuntimeError(f"{vapi_md_path}: unterminated fenced code block after {marker!r}")
    return after[fence_start:fence_end].strip("\n")


def build_server_config(
    server_url: str, *, secret: Optional[str], credential_id: Optional[str]
) -> dict:
    """`credential_id` (a dashboard-created Custom Credential) takes
    priority over `secret` (the legacy inline field) if both are somehow
    set — see this file's module docstring for why both exist."""
    if not server_url:
        raise ValueError("server_url is required (VAPI_SERVER_URL)")
    server: dict[str, Any] = {"url": server_url}
    if credential_id:
        server["credentialId"] = credential_id
    elif secret:
        server["secret"] = secret
    else:
        raise ValueError(
            "Neither a webhook secret nor a credential ID was provided. "
            "Every real Vapi tool call would then arrive at "
            "app/core/security/vapi_webhook_auth.py with no way to "
            "authenticate — it would correctly reject every call (fails "
            "closed, per that module's own docstring), so this would not "
            "be a security hole, but it would mean nothing works. Set "
            "VAPI_WEBHOOK_SECRET or VAPI_WEBHOOK_CREDENTIAL_ID."
        )
    return server


def build_function_tool_payload(schema: VapiToolSchema, server: Mapping[str, Any]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": schema.name,
            "description": schema.description,
            "parameters": dict(schema.parameters),
        },
        "server": dict(server),
    }


def build_transfer_call_tool_payload(destination_number: str, message: str) -> dict:
    if not destination_number:
        raise ValueError("destination_number is required")
    return {
        "type": "transferCall",
        "destinations": [
            {"type": "number", "number": destination_number, "message": message}
        ],
    }


def build_assistant_payload(
    *,
    name: str,
    server: Mapping[str, Any],
    tool_ids: list,
    model_provider: str,
    model_name: str,
    system_prompt: str,
) -> dict:
    return {
        "name": name,
        "server": dict(server),
        "model": {
            "provider": model_provider,
            "model": model_name,
            "toolIds": list(tool_ids),
            "messages": [{"role": "system", "content": system_prompt}],
        },
    }


def plan_function_tool_upserts(
    schemas: Mapping[str, VapiToolSchema],
    server: Mapping[str, Any],
    existing_tools_by_name: Mapping[str, str],
) -> "list[dict]":
    """Returns one plan entry per schema: {"name", "action" ("create" or
    "update"), "existing_id" (or None), "payload"}. Pure — takes the
    existing-tools snapshot as data rather than fetching it, so this is
    testable without a network call; the caller is responsible for
    getting that snapshot from a real GET /tool when actually applying."""
    plan = []
    for schema in schemas.values():
        existing_id = existing_tools_by_name.get(schema.name)
        plan.append(
            {
                "name": schema.name,
                "action": "update" if existing_id else "create",
                "existing_id": existing_id,
                "payload": build_function_tool_payload(schema, server),
            }
        )
    return plan


def plan_transfer_call_upsert(
    destination_number: Optional[str],
    message: str,
    existing_transfer_tool_ids: "list[str]",
) -> Optional[dict]:
    """Returns None if no destination number was supplied (this step is
    skipped entirely, matching "only attempted if a destination number is
    supplied" in the module docstring). Raises if more than one
    transferCall tool already exists on the account — this script refuses
    to guess which one to update, matching MASTER_RULES' "don't guess"
    discipline; that has to be resolved by a human in the Vapi dashboard."""
    if not destination_number:
        return None
    if len(existing_transfer_tool_ids) > 1:
        raise RuntimeError(
            f"{len(existing_transfer_tool_ids)} transferCall tools already "
            "exist on this Vapi account — refusing to guess which one to "
            "update. Resolve manually in the Vapi dashboard (delete the "
            "extras or note which one to keep), then re-run."
        )
    existing_id = existing_transfer_tool_ids[0] if existing_transfer_tool_ids else None
    return {
        "action": "update" if existing_id else "create",
        "existing_id": existing_id,
        "payload": build_transfer_call_tool_payload(destination_number, message),
    }


# ===========================================================================
# Networked layer — httpx is imported lazily, only inside VapiClient, so
# every function above this line (and therefore the default, no --apply,
# invocation of main() below) works without httpx installed at all.
# ===========================================================================


class VapiClient:
    """Thin wrapper over https://api.vapi.ai. Constructing this imports
    httpx — deliberately deferred so the rest of this module stays
    importable (and testable) without it. NEVER EXERCISED against a real
    account or even a real httpx install in this sandbox (`403
    host_not_allowed` on api.vapi.ai, confirmed again this session;
    `ModuleNotFoundError: No module named 'httpx'` here — same blocker as
    every apps/api/app/providers/* real-integration file)."""

    def __init__(self, api_key: str, base_url: str = VAPI_API_BASE) -> None:
        import httpx  # deferred — see class docstring

        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    def list_tools(self) -> "list[dict]":
        # NOTE: pagination has not been verified against a real account —
        # if this account ever has enough tools to paginate, GET /tool's
        # response shape for a page-2+ cursor needs confirming against
        # docs.vapi.ai before trusting this to see every tool. For the 22
        # tools this script manages, that is very unlikely to matter, but
        # don't silently assume it for an account with many more tools.
        resp = self._client.get("/tool")
        resp.raise_for_status()
        return resp.json()

    def create_tool(self, payload: dict) -> dict:
        resp = self._client.post("/tool", json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_tool(self, tool_id: str, payload: dict) -> dict:
        resp = self._client.patch(f"/tool/{tool_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def create_assistant(self, payload: dict) -> dict:
        resp = self._client.post("/assistant", json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_assistant(self, assistant_id: str, payload: dict) -> dict:
        resp = self._client.patch(f"/assistant/{assistant_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_phone_number(self, phone_number_id: str, payload: dict) -> dict:
        resp = self._client.patch(f"/phone-number/{phone_number_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()


def _index_existing_tools(existing_tools: "list[dict]") -> "tuple[dict, list]":
    """Splits GET /tool's response into (function-tools-by-name,
    transfer-call-tool-ids) — the two things the upsert planners need."""
    by_name: dict = {}
    transfer_ids: list = []
    for t in existing_tools:
        if t.get("type") == "function" and isinstance(t.get("function"), dict):
            name = t["function"].get("name")
            if name:
                by_name[name] = t.get("id")
        elif t.get("type") == "transferCall":
            transfer_ids.append(t.get("id"))
    return by_name, transfer_ids


def apply_plan(client: VapiClient, function_plan: "list[dict]", transfer_plan: Optional[dict]) -> "tuple[list[str], Optional[str]]":
    tool_ids = []
    for entry in function_plan:
        if entry["action"] == "update":
            result = client.update_tool(entry["existing_id"], entry["payload"])
            tool_ids.append(entry["existing_id"])
        else:
            result = client.create_tool(entry["payload"])
            tool_ids.append(result["id"])
        print(f"  [{entry['action']}] function tool: {entry['name']} -> {tool_ids[-1]}")

    transfer_tool_id = None
    if transfer_plan is not None:
        if transfer_plan["action"] == "update":
            client.update_tool(transfer_plan["existing_id"], transfer_plan["payload"])
            transfer_tool_id = transfer_plan["existing_id"]
        else:
            result = client.create_tool(transfer_plan["payload"])
            transfer_tool_id = result["id"]
        print(f"  [{transfer_plan['action']}] transferCall tool -> {transfer_tool_id}")

    return tool_ids, transfer_tool_id


def _load_env() -> dict:
    """Reads the same environment variable names app.core.config.Settings
    defines for Vapi, directly via os.environ — see the import comment
    above for why this doesn't go through get_settings() itself."""
    return {
        "vapi_api_key": os.environ.get("VAPI_API_KEY") or None,
        "vapi_webhook_secret": os.environ.get("VAPI_WEBHOOK_SECRET") or None,
        "vapi_assistant_id": os.environ.get("VAPI_ASSISTANT_ID") or None,
        "vapi_phone_number_id": os.environ.get("VAPI_PHONE_NUMBER_ID") or None,
    }


# ===========================================================================
# CLI
# ===========================================================================


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually call the Vapi API. Without this flag, only the "
        "planned payloads are printed and nothing is sent (default).",
    )
    parser.add_argument(
        "--model-provider",
        required=True,
        help="Vapi model.provider, e.g. 'openai' or 'anthropic'. Required, "
        "not defaulted — docs/VAPI.md deliberately leaves this "
        "provider-agnostic; this script won't choose for you.",
    )
    parser.add_argument(
        "--model-name",
        required=True,
        help="Vapi model.model, e.g. 'gpt-4o'. Required for the same "
        "reason as --model-provider.",
    )
    parser.add_argument(
        "--assistant-name",
        default="Charter123 Booking Assistant",
        help="Assistant display name (default: %(default)s).",
    )
    parser.add_argument(
        "--transfer-number",
        default=os.environ.get("VAPI_TRANSFER_NUMBER"),
        help="Destination phone number (E.164) for the native transferCall "
        "tool. If omitted (and VAPI_TRANSFER_NUMBER is unset), the "
        "transferCall tool step is skipped entirely — transfer_to_human "
        "will keep logging escalations with nothing to actually connect "
        "them to, exactly as docs/VAPI.md's 'Transfer to human' section "
        "already describes as the current state.",
    )
    parser.add_argument(
        "--transfer-message",
        default=os.environ.get("VAPI_TRANSFER_MESSAGE", _DEFAULT_TRANSFER_MESSAGE),
        help="What the assistant says while transferring (default: %(default)r).",
    )
    return parser


def main(argv: Optional["list[str]"] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    env = _load_env()

    server_url = os.environ.get("VAPI_SERVER_URL")
    credential_id = os.environ.get("VAPI_WEBHOOK_CREDENTIAL_ID")

    system_prompt = load_suggested_system_prompt()

    print("=" * 78)
    print("Charter123 / Vapi setup — spec §51, docs/TASK_BOARD.md T-4")
    print("=" * 78)
    print(f"Mode: {'APPLY (will call the Vapi API)' if args.apply else 'DRY RUN (plan only, no network calls)'}")
    print(f"Tools to manage: {len(VAPI_TOOL_SCHEMAS)} function tools "
          f"+ {'1 transferCall tool' if args.transfer_number else 'no transferCall tool (no --transfer-number)'}")
    print(f"Assistant: {'update ' + env['vapi_assistant_id'] if env['vapi_assistant_id'] else 'create new'}")
    print(f"Phone number: {'attach ' + env['vapi_phone_number_id'] if env['vapi_phone_number_id'] else 'none configured (VAPI_PHONE_NUMBER_ID unset)'}")
    print()

    if not args.apply:
        # Dry run needs no VAPI_API_KEY/VAPI_SERVER_URL/secret at all — it
        # only needs to prove what WOULD be built. Existing-tool state is
        # unknown without a real GET /tool, so every entry is shown as a
        # "create" here; the real create-vs-update decision happens only
        # at --apply time against the live account. Said explicitly so
        # this is never mistaken for a truthful account-state diff.
        placeholder_server = {"url": server_url or "<VAPI_SERVER_URL not set>", "secret": "<redacted>"}
        function_plan = plan_function_tool_upserts(VAPI_TOOL_SCHEMAS, placeholder_server, {})
        transfer_plan = plan_transfer_call_upsert(args.transfer_number, args.transfer_message, [])
        assistant_payload = build_assistant_payload(
            name=args.assistant_name,
            server=placeholder_server,
            tool_ids=["<tool-id-1>", "...", f"<{len(VAPI_TOOL_SCHEMAS)} total>"],
            model_provider=args.model_provider,
            model_name=args.model_name,
            system_prompt=system_prompt,
        )
        print("Planned (assuming a fresh account — see note above):")
        for entry in function_plan:
            print(f"  [{entry['action']}] {entry['name']}")
        if transfer_plan:
            print(f"  [{transfer_plan['action']}] transferCall -> {args.transfer_number}")
        print()
        print("Assistant payload that would be sent:")
        print(json.dumps(assistant_payload, indent=2))
        print()
        print("This was a dry run. Nothing was sent. Re-run with --apply to "
              "actually call the Vapi API (requires VAPI_API_KEY, "
              "VAPI_SERVER_URL, and VAPI_WEBHOOK_SECRET or "
              "VAPI_WEBHOOK_CREDENTIAL_ID to be set).")
        return 0

    # --- --apply path: everything below this line needs httpx + network +
    # real credentials, none of which exist in the sandbox this was
    # written in. Written and reviewed; NOT executed. ----------------------
    if not env['vapi_api_key']:
        print("ERROR: VAPI_API_KEY is not set.", file=sys.stderr)
        return 1
    if not server_url:
        print("ERROR: VAPI_SERVER_URL is not set (e.g. "
              "https://your-domain.com/api/v1/vapi/webhook).", file=sys.stderr)
        return 1
    try:
        server = build_server_config(
            server_url, secret=env['vapi_webhook_secret'], credential_id=credential_id
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    client = VapiClient(env['vapi_api_key'])
    try:
        existing_tools = client.list_tools()
        existing_by_name, existing_transfer_ids = _index_existing_tools(existing_tools)

        function_plan = plan_function_tool_upserts(VAPI_TOOL_SCHEMAS, server, existing_by_name)
        transfer_plan = plan_transfer_call_upsert(
            args.transfer_number, args.transfer_message, existing_transfer_ids
        )

        print(f"Upserting {len(function_plan)} function tools" + (" and 1 transferCall tool..." if transfer_plan else "..."))
        tool_ids, transfer_tool_id = apply_plan(client, function_plan, transfer_plan)
        if transfer_tool_id:
            tool_ids.append(transfer_tool_id)

        assistant_payload = build_assistant_payload(
            name=args.assistant_name,
            server=server,
            tool_ids=tool_ids,
            model_provider=args.model_provider,
            model_name=args.model_name,
            system_prompt=system_prompt,
        )

        if env['vapi_assistant_id']:
            client.update_assistant(env['vapi_assistant_id'], assistant_payload)
            assistant_id = env['vapi_assistant_id']
            print(f"Updated assistant {assistant_id}")
        else:
            result = client.create_assistant(assistant_payload)
            assistant_id = result["id"]
            print(f"Created new assistant: {assistant_id}")
            print(f"  ACTION REQUIRED: set VAPI_ASSISTANT_ID={assistant_id} in your .env — "
                  "re-running this script without it will create ANOTHER assistant "
                  "instead of updating this one.")

        if env['vapi_phone_number_id']:
            client.update_phone_number(env['vapi_phone_number_id'], {"assistantId": assistant_id})
            print(f"Attached phone number {env['vapi_phone_number_id']} -> assistant {assistant_id}")
        else:
            print("No VAPI_PHONE_NUMBER_ID set — skipped phone number attachment. "
                  "This is WBS-2.3/T-4's 'connect a real phone number' step, done "
                  "either by buying/importing a number in the Vapi dashboard first "
                  "(get its ID) or manually attaching this assistant to an existing "
                  "number there.")
    finally:
        client.close()

    print()
    print("Setup calls complete. This is NOT the same as a verified "
          "integration — WBS-2.4/2.5 (a real inbound test call, and a real "
          "transfer_to_human -> native transferCall handoff) still need a "
          "human to actually call the number and listen. See docs/VAPI.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
