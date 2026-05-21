# ROADMAP — Framework Interactive Completion (sibling track)

> **Track id:** `framework_interactive` (phases `FI-1 … FI-7`). Sibling to the thesis eval track, **not**
> a rewrite of phases 0–38. Aviona consumes these APIs; it owns no orchestration after this track lands.

---

## Why this track exists (root cause)

Aviona v2 added `terminate{user_message, turn_type}` and an "interactive mode," but **completion was never
made a first-class Decision-Cycle concern** (`FRAMEWORK_ROOT_CAUSES.md` §1). The interactive path in
`orchestration/session.py::_run_interactive_executor_turn` is an ad-hoc imperative loop that wraps executor
cycles with free-text `reflection_guidance` and a post-hoc `_synthesize_interactive_user_message`. The
consequences are the live failures in `PROBLEM_INVENTORY.md`:

- The agent runs read-only tools and **never emits `terminate`** (F01); the loop then either scrapes the last
  tool snapshot (a `list_dir` listing marked `ok` — R05, R06, R10, R14, R15) or returns nothing (R07, R08).
- **Turn type and budget are inferred by Aviona keyword heuristics** (`infer_interactive_max_steps`, F03/A04)
  instead of declared by the agent and enforced by Python (F04).
- **Tool output is not salient in the next prompt** (free-text `reflection_guidance`, not a typed channel),
  so the model repeats identical tools (F08, F06).
- **Compound goals** (write test → run → show) get one flat `max_steps` and one turn type (F19), so they
  exhaust budget mid-task (R15).
- **Permissions** block run/test prompts (F11, R14), and the executor advertises tools it does not have
  (`glob`, `search_codebase` — F10, §6).

The fix is **not** more product patches. It is a typed **Interactive Completion Protocol (ICP)** inside the
control layer. Every change below keeps the eight rules in `ARCHITECTURE_RULES.md`: the SLM still never chooses
transitions — it *proposes typed data* (`turn_type`, `terminate`, `handoff`) and the ICP, a **Python**
sub-state-machine, decides transitions, budgets, permissions, and dedup. The finalizer in FI-4 is a normal
Decision-Cycle LLM call (rule 4); tool output is truncated before prompts (rule 5); `user_message` is only
ever produced by the agent, never scraped (kills the patterns deleted in v2-4).

### Insertion point — recommended Option B (justified)

`ROADMAP_CONTEXT.md` offers three insertion options. **Recommend Option B: a sibling track that must go green
before thesis phase 39 resumes.** Rationale: phase 39 (LaTeX table automation) does not depend on interactive
turns, but FI-1…FI-7 touch the *same* files phase 39's authors would otherwise re-touch
(`session.py`, `cycle.py`, `self_check.py`, `models.py`), so finishing interactive first avoids rework; the
batch eval phases 30–38 are already done and unaffected. Bonus: a typed completion protocol is a legitimate
**RQ2 control-logic contribution** (deterministic control compensating for SLM weakness), so this track
strengthens the thesis narrative rather than competing with it. Do **not** block batch eval on it.

---

## Phase Overview

```
FI-1 → Agent-declared turn_type on cycle 1 binds budget/permissions (Python-enforced)   [F03,F04,A04]
FI-2 → Typed tool-result channel in working memory (replaces reflection_guidance)        [F05,F08,F14,F20]
FI-3 → Interactive Completion Protocol: mandatory terminate + repeat-tool dedup           [F01,F06,F16]
FI-4 → Finalizer cycle (typed self-summary) + honest-failure floor; outcome contract fix  [F02,F15,F14]
FI-5 → Compound turns (inspect→edit→verify) via typed handoff phase machine               [F19,F13,F12]
FI-6 → Inspect-run permission policy + executor tool parity (glob/search or skills)       [F10,F11,§6]
FI-7 → Interactive failure-mode mock test suite (reproduce the loops in CI)               [test gap]
```

Contract: **Goal → Tasks → Acceptance tests → Commit**. Each phase is one concern, ≤5 tasks, mocked unit tests,
one commit (`RECOMMENDED_PRINCIPLES.md` phase sizing). No live API in this track except where a phase is marked
`[REQUIRES_USER_INPUT]` (none here are; live coverage lives in Aviona v3).

---

## FI-1 — Agent-declared `turn_type` on cycle 1 binds budget & permissions

**Goal:** The agent's **first** proposal carries a typed `turn_type` (`answer|inspect|edit|build`); Python uses
that declaration — never goal-text regex — to set the step budget, the read-only flag, and the permission
profile for the turn. Fixes the keyword-heuristic budget (F03/F04/A04, the `show`-token mis-budget in R15).

### Tasks
- `src/framework/control/models.py` — add `turn_type: Literal["answer","inspect","edit","build"]` to the
  proposal/`terminate` schema; add a typed `InteractiveTurnState` (declared_type, phase, budgets, read_only).
- `src/framework/orchestration/session.py` — `_run_interactive_executor_turn` reads the cycle-1 declared
  `turn_type` and binds a framework-owned budget map + `interactive_read_only` + permission profile from it.
  **Delete** reliance on any Aviona-passed `max_steps` heuristic.
- `src/framework/control/cycle.py` — first-proposal format hint requires `turn_type` (anchor-first, rule 6);
  missing/invalid `turn_type` raises a typed self-check issue and re-prompts (no default-by-keyword).
- Framework default budget map (single source of truth): `answer:1, inspect:4, edit:6, build:15` in
  `configs/models.yaml` under `interactive`.

### Acceptance tests
```bash
pytest tests/unit/test_interactive_turn_type_binding.py
# declares inspect → budget=4, read_only=True, permission=read-only
# declares edit    → write tools allowed, budget=6
# missing turn_type on cycle 1 → self_check issue 'turn_type_required' → corrective re-prompt (no goal regex)
```

### Commit
```
framework-interactive-1: agent-declared turn_type binds budget/permissions (Python-enforced)
```

---

## FI-2 — Typed tool-result channel in working memory

**Goal:** Truncated tool outputs enter the next prompt as a **typed `ToolResultMessage` block** in the
working-memory anchor, replacing the free-text `reflection_guidance` injection. Fixes "model repeats the same
tool because the output wasn't salient" (F08), the ad-hoc string state (F05/F14), and gives the agent the prior
turn's results so it can resolve anaphora itself ("its content", "this code") without a Python coreference
resolver (F20).

### Tasks
- `src/framework/memory/stores.py` — typed `ToolResultEntry` (tool, path, truncated_output, ok); append-only
  (rule 7).
- `src/framework/memory/working_memory.py` — `WorkingMemoryBuilder` renders a `[TOOL RESULTS]` section
  (most-recent-first, truncated per rule 5) and a short `[RECENT TURNS]` recap so references resolve.
- `src/framework/orchestration/session.py` — remove `reflection_guidance` free-text injection from the
  interactive path; route tool results through the typed channel only.
- `--debug` metric: log whether tool output for cycle *N* is present in the prompt for cycle *N+1*.

### Acceptance tests
```bash
pytest tests/unit/test_working_memory_contains_tool_output.py
# after a read_file tool_call, the next built prompt contains the (truncated) file body in [TOOL RESULTS]
# reflection_guidance string is not used anywhere in the interactive path
# [RECENT TURNS] includes the prior turn's edited path (anaphora support)
```

### Commit
```
framework-interactive-2: typed tool-result channel in working memory (replaces reflection_guidance)
```

---

## FI-3 — Interactive Completion Protocol: mandatory terminate + repeat-tool dedup

**Goal:** After a successful tool call the Decision Cycle enters a Python-enforced sub-state where the next
proposal **must** be `terminate{user_message}` or a *new* (deduped) tool; an identical repeat tool
(`tool:path` key) is rejected as a typed self-check issue. This is the core fix for F01/F06/F16 and the
`list_dir × 3` loops (R05/R06/R10/R14/R15). Replaces `_synthesize_interactive_user_message` scraping.

### Tasks
- `src/framework/control/interactive.py` (new) — pure-Python ICP sub-machine:
  `GATHER → (TOOL_OK) → MUST_FINALIZE_OR_CONTINUE`. `continue` requires a tool whose `tool:path` key was not
  used this turn; otherwise the proposal is rejected.
- `src/framework/control/self_check.py` — typed issues `must_terminate_after_tool`, `repeat_tool`,
  `must_terminate_after_edit`; corrective re-prompt carries the issue (not free text).
- `src/framework/orchestration/session.py` — drive the interactive turn through the ICP machine; **delete**
  `_synthesize_interactive_user_message` as the default completion path.
- Transitions remain Python (rule 3); the agent only proposes `terminate`/`tool_call`.

### Acceptance tests
```bash
pytest tests/unit/test_icp_terminate_after_tool.py
pytest tests/unit/test_list_dir_repeat_blocked_then_terminate.py
# mock list_dir then identical list_dir → 2nd rejected (repeat_tool) → forced toward terminate
# mock read_file → ok → next proposal must be terminate; tool_call of new path allowed once
# non-list goal: a list_dir result is NEVER emitted as user_message
```

### Commit
```
framework-interactive-3: Interactive Completion Protocol (mandatory terminate, repeat-tool dedup)
```

---

## FI-4 — Finalizer cycle (typed self-summary) + honest-failure floor

**Goal:** When tool work is done but the agent did not terminate, run **one** constrained finalizer Decision
Cycle whose only legal output is `terminate{user_message, turn_type}`, built from the typed tool-result channel
(FI-2). If the finalizer also fails, return an honest `unresolvable` → REPL shows `! reason`. This is
`FRAMEWORK_ROOT_CAUSES.md` §8 **option C** (agent self-summary), not scraping or hardcode, and it fixes the
contract drift in F15. Resolves the tension in `RECOMMENDED_PRINCIPLES.md`: strict honest failure is the floor;
the finalizer is the only recovery and it is still an LLM call through the Decision Cycle (rule 4).

### Tasks
- `src/framework/orchestration/session.py` — finalizer step: a single bounded cycle with a constrained prompt
  (only `terminate` allowed) seeded with `[TOOL RESULTS]`; runs once when ICP ends without terminate.
- `src/framework/control/models.py` — `SessionOutcome.user_message` is populated **only** from a `terminate`
  decision (remove all out-of-band population, F15).
- `configs/models.yaml` — `interactive.finalizer: on|off` (off = immediate `unresolvable`, strict mode A).
- No `list_dir`→message synthesis remains (`RECOMMENDED_PRINCIPLES.md` synthesis table: rejected for non-list).

### Acceptance tests
```bash
pytest tests/unit/test_finalizer_forces_terminate.py
# tool ran, no terminate, finalizer:on  → finalizer cycle emits terminate from tool results
# finalizer also fails                  → outcome unresolvable, user_message == "" (honest !)
# finalizer:off                         → immediate unresolvable (strict)
# SessionOutcome.user_message is empty unless a terminate decision exists
```

### Commit
```
framework-interactive-4: finalizer cycle for typed self-summary; honest-failure floor; outcome contract fix
```

---

## FI-5 — Compound turns (inspect → edit → verify) via typed handoff phase machine

**Goal:** Support multi-phase goals (read→answer, edit→verify→message, write test→pytest→show) as a typed
sub-turn progression driven by the agent's `handoff`, with Python allocating **per-phase** budgets — not one
flat `max_steps` for the whole turn (F19, F12, F13; R12, R15).

### Tasks
- `src/framework/control/models.py` — typed `handoff{reason: "needs_edit"|"needs_run"|"needs_plan"}`.
- `src/framework/orchestration/session.py` / workflow — Python phase machine: `inspect` phase, on
  `needs_edit` → promote to `edit` phase (edit budget) → on `needs_run` → run/verify step → `terminate`;
  `build` promotes to the planner on `needs_plan` (existing promotion). Each phase has its own budget.
- Budgets accrue per phase so an edit that first reads does not exhaust the inspect cap.
- Promotion is keyed on the typed `handoff` only — never goal substrings (`ARCHITECTURE_RULES.md` "not allowed").

### Acceptance tests
```bash
pytest tests/integration/test_compound_edit_run.py
# write+run goal: edit phase budget used; a verify (pytest/compile) runs before terminate
# inspect that needs to edit promotes via handoff(needs_edit), not goal regex
# build goal promotes to planner via handoff(needs_plan)
```

### Commit
```
framework-interactive-5: compound turns via typed handoff phase machine
```

---

## FI-6 — Inspect-run permission policy + executor tool parity

**Goal:** Let declared `inspect` turns run **read-only** commands (pytest, `python -c`) through a typed policy
(not goal regex), and stop advertising tools the executor lacks (F10, F11, §6; R14, R15).

### Tasks
- `src/framework/error_control/sandbox.py` — classify run-safe/read-only commands; expose a `run_tests`/`run`
  tool kind that is auto-allowed within the workspace for declared `inspect` turns (still write-guarded,
  sandboxed, output truncated). Policy is keyed on declared `turn_type`, not goal text.
- `src/framework/orchestration/executor.py` — prefer the existing pytest `run_tests` tool over raw `shell`;
  **either** implement minimal `glob`/`search_codebase` **or** remove them from prompts and update the
  executor skill YAML so the agent chains `list_dir → read_file → terminate` (pick one in the commit; default:
  add `glob`, remove `search_codebase` from hints until implemented).
- Ensure every tool named in any prompt hint exists in the executor (parity test).

### Acceptance tests
```bash
pytest tests/unit/test_shell_inspect_permission_policy.py
pytest tests/unit/test_executor_tool_parity.py
# pytest/python -c run under inspect policy without 'ask'; writes still require edit turn + permission
# no prompt hint references a tool the executor does not implement
```

### Commit
```
framework-interactive-6: inspect-run permission policy + executor tool parity
```

---

## FI-7 — Interactive failure-mode mock test suite

**Goal:** Lock the protocol with **mock SLM queues that reproduce the real failure modes** so CI catches
regressions without live API. Closes the L2 gap noted in `TEST_COVERAGE_GAPS.md` ("mocks queue terminate
immediately, never reproduce loops").

### Tasks
- `tests/unit/_mock_slm_queue.py` (new) — a scripted SLM that emits an ordered list of proposals (loop, then
  terminate; tool-without-terminate; edit-without-terminate; compound).
- Tests mapping to `PROBLEM_INVENTORY.md` rows: `test_no_synthesis_from_list_dir_for_explore_goal` (R10),
  `test_read_then_terminate` (R06/R07/R08), `test_partial_read_honest_limit` (R11),
  `test_edit_then_verify_then_terminate` (R12), `test_compound_test_run_show` (R15),
  `test_anaphora_uses_recent_turn_context` (R13).
- Wire into `scripts/test-aviona.ps1` L2 and `pytest -m "not e2e"`.

### Acceptance tests
```bash
pytest tests/unit/test_interactive_*.py tests/integration/test_interactive_turn.py
# every PROBLEM_INVENTORY loop pattern: ends in correct terminate OR honest unresolvable — never wrong ok
```

### Commit
```
framework-interactive-7: interactive failure-mode mock test suite
```

---

## Eval / test strategy (beyond the 9 live prompts, no brittle string matching)

- **L2 mocked (CI, every commit):** the FI-7 failure-mode queues + the contract matrix. These assert *protocol
  behavior* (terminate vs honest fail, dedup, budget binding), not phrasings — so they don't regress into the
  deleted v2-6 substring journeys.
- **L3 live (nightly / on demand, `[REQUIRES_USER_INPUT]` for API budget):** the expanded matrix from
  `SESSION_EVIDENCE.md` (explore-md, main-file, partial-read, run-input, edit+read chain, test+run+show,
  anaphora). `must_contain` checks live **only at the harness layer** (`live_gate.py`) — never as routing.
- **CI split:** `pytest -m "not e2e"` runs all mocked interactive tests; live matrix is `@pytest.mark.e2e`,
  excluded from default CI, run via Aviona v3's expanded gate.

## What NOT to build (re-stated; do not reintroduce)

No `classify_goal`/regex routing; no `intent.py` phrase→action; no fixture aliases (`main file`→main.py); no
pre-turn disk reads from goal text; no `effects.py`/`fallbacks.py` scrape stack; no auto-revert; no
`list_dir`-output-as-`user_message` for non-list goals; no goal substring → file path / shell command / skip
LLM (`ARCHITECTURE_RULES.md`). The only completion paths are: agent `terminate{user_message}`, the FI-4
finalizer cycle, or honest `unresolvable` → `! reason`.

## One-command test gates (recap)

```bash
FI-1: pytest tests/unit/test_interactive_turn_type_binding.py
FI-2: pytest tests/unit/test_working_memory_contains_tool_output.py
FI-3: pytest tests/unit/test_icp_terminate_after_tool.py tests/unit/test_list_dir_repeat_blocked_then_terminate.py
FI-4: pytest tests/unit/test_finalizer_forces_terminate.py
FI-5: pytest tests/integration/test_compound_edit_run.py
FI-6: pytest tests/unit/test_shell_inspect_permission_policy.py tests/unit/test_executor_tool_parity.py
FI-7: pytest tests/unit/test_interactive_*.py tests/integration/test_interactive_turn.py
```

> **Dependency order:** FI-1 → FI-2 → FI-3 → FI-4 are the critical path (declare type → see tool output →
> require terminate → recover or fail honestly). FI-5/FI-6 extend to compound and run/test goals. FI-7 locks it.
> Thesis phase 39 resumes once FI-7 and the Aviona v3 live gate (`aviona-v3-3`) are green.
