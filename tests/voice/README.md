# tests/voice

The voice conversation test suite from the original spec's §56 (e.g.
"customer says 'book it' with no quoted flight -> agent must not book")
is written and passing, as of T-7 (docs/TASK_BOARD.md, WBS-6.2) — but it
lives at `apps/api/tests/test_voice_conversation_core.py`, not in this
directory, since it's dependency-free (stdlib + this repo only, same
tier as `apps/api/tests/test_core_logic.py`) and exercises `apps/api/
app/core/vapi/`'s own argument-mapping/authorization/provider code
directly, the same layer every other `*_core.py` suite in this project
lives beside. Run it with:

    cd apps/api && python3 -m unittest tests.test_voice_conversation_core -v

Read that file's own module docstring before assuming it proves more
than it does: it tests the backend guarantee behind each spec-§56
scenario (the thing that holds true regardless of what the LLM says or
tries), not the live Vapi assistant's actual conversational behavior —
that half genuinely needs WBS-2.2-2.5's live phone number and account,
which remain BLOCKED, same as before this task.

This directory is kept as a placeholder for whatever that live-call
layer becomes once WBS-2 unblocks — "the 7 example test cases in the
spec" per WBS-6.2's own words is really 6 as documented, plus "whatever
else the Assistant's real behavior surfaces once WBS-2 gives it a live
phone number to test against."
