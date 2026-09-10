# scripts/

One-off operational scripts.

- **`setup_vapi.py`** (spec §51, `docs/TASK_BOARD.md` T-4, written
  2026-09-09) — creates/updates the 21 registered Vapi tools, the native
  `transferCall` tool, the Assistant, and phone-number attachment on a
  real Vapi account. **Written and unit-tested (`test_setup_vapi.py`,
  24 tests, dependency-free); never run against a real Vapi account** —
  see the script's own module docstring and `docs/TASK_BOARD.md`'s T-4
  entry before using it. Defaults to a dry run that prints the full plan
  without calling the network; pass `--apply` to actually call the API.
- **`test_setup_vapi.py`** — dependency-free unit tests for
  `setup_vapi.py`'s pure logic (payload construction, upsert planning,
  the system-prompt loader). Run with:
  `cd scripts && python3 -m unittest test_setup_vapi -v`
