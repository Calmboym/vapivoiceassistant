# Charter123 — Session Bootstrap Prompt

Paste everything in the box below at the start of every new Claude
development session on this project, before describing what you want
done this session.

---

```
You are continuing development on Charter123 AI, an existing repository.
Do not rely on this chat's prior history if there is any — a compacted
context window or a different session may be missing something that made
an earlier decision correct. Do not assume a feature is complete because
a document says so, and do not assume a feature is missing because a
checklist says so. The repository is the primary evidence for
implementation status; documents are evidence for intent and history.

Before writing or changing anything, read, in this order:

1. docs/PROJECT_ROADMAP.md — canonical reconciled baseline. Read this
   fully, especially "Current Position" and the "Contradictions found"
   section — some of them are still open.
2. docs/PROJECT_STATE.md — subsystem-by-subsystem current state.
3. docs/TASK_BOARD.md — what's actually authorized right now. A
   capability existing in the roadmap does NOT mean it's authorized to
   be built this session.
4. docs/MASTER_RULES.md — non-negotiable engineering invariants. These
   don't expire when a phase ends.
5. The relevant section of docs/WORK_BREAKDOWN_STRUCTURE.md for whatever
   task is authorized.
6. The most recent applicable handoff — either a root-level
   PROJECT_HANDOFF_PHASE_*.md or the latest file under docs/handoffs/ —
   for the specific engineering context and bug history behind whatever
   you're about to touch. Treat handoffs as historical transition
   context, written by a specific session at a specific time — not as
   more authoritative than the repository if the two disagree.

Then inspect the actual relevant source code — models, services, routes,
tests, migrations — before implementing anything. Never implement based
on documentation alone.

Before writing code, state your understanding back, briefly:
- Last completed milestone
- Current authorized task (quote the exact task-board entry)
- Relevant constraints from MASTER_RULES.md
- Known risks/blockers that apply to this task

Rules while working:
- Do not redesign architecture without evidence that it's broken.
- Do not silently change phase numbering or move functionality between
  phases — if you think the numbering is wrong, say so and propose a
  fix in docs/PROJECT_ROADMAP.md; don't just renumber quietly.
- Do not implement future-phase functionality beyond what's authorized
  in docs/TASK_BOARD.md.
- Do not mark work "complete" or "tested" without it actually having run
  — distinguish Verified locally / Written, not executed / Requires
  external verification, explicitly, every time.
- Do not fabricate integrations, credentials, runtime results, or test
  output.
- Never trust a client-supplied identity header/field as authorization —
  see MASTER_RULES.md §2.
- Never let a mutation with real consequences (booking, cancellation,
  payment) execute without the explicit-confirmation pattern already
  established — see MASTER_RULES.md §3.
- Preserve existing working functionality; don't delete something to
  simplify a task.

After implementing an authorized task:
1. Run the relevant tests — at minimum the full dependency-free suite:
   cd apps/api && python3 -m unittest tests.test_core_logic
   tests.test_security_core tests.test_vapi_core tests.test_payments_core
   tests.test_api_security tests.test_vapi_api -v
2. Run type-checking/lint/build where applicable.
3. Verify migrations, API contracts, and security boundaries for
   whatever you touched.
4. Update docs/PROJECT_STATE.md and docs/TASK_BOARD.md to reflect what
   changed.
5. Update docs/PROJECT_ROADMAP.md if the project baseline itself changed
   (a phase completed, a new contradiction was found, a documented gap
   was closed).
6. Create a new milestone/phase handoff under docs/handoffs/ if a
   milestone or phase completed — do not create one for incomplete work
   unless explicitly asked, and do not overwrite an existing frozen
   handoff.

If documentation and implementation disagree, or if the currently
authorized task is unclear: stop, report the discrepancy, and ask —
don't guess and don't start unrelated work while waiting.
```
