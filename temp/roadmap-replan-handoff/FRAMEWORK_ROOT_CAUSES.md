# Framework Root Causes (Thesis Layer)

These are **structural** issues in `src/framework/`. Aviona symptoms should be fixed here, not with product-layer patches.

---

## 1. Identity mismatch (documented in ROADMAP_PRODUCTION_AVIONA_V2.md §1)

| Thesis engine (original) | Conversational REPL (Aviona) |
|--------------------------|------------------------------|
| Success = verifier passes on workspace | Success = user got correct `user_message` |
| SessionOutcome = task state | User sees REPL detail line |
| Full graph default | Cheap single-turn default |

**v2 added** `terminate.user_message` and interactive mode, but **completion is not enforced** inside the Decision Cycle — the interactive loop in `session.py` wraps executor calls with ad-hoc retries and synthesis.

**Replan should:** Make user-visible completion a first-class framework concern, not an Aviona afterthought.

---

## 2. Missing "tool → terminate" protocol

**Observed flow (broken):**
```
cycle 1: tool_call list_dir  → ok
cycle 2: tool_call list_dir  → ok (repeat)
cycle 3: tool_call list_dir  → budget exhausted
→ synthesis or missing user_message
```

**Expected flow (framework-level):**
```
cycle 1: tool_call read_file → ok, tool output in working memory
cycle 2: terminate{user_message, turn_type:inspect}
```

**Current mitigations (insufficient):**
- `read_tools_used` dedup key
- `reflection_guidance` free-text string in state
- `_synthesize_interactive_user_message` from last tool snapshot

**Replan should:** Decision Cycle or interactive engine state machine with typed transitions:
- `TOOL_OK` → next proposal must be `terminate` or explicit `continue_inspect` with new tool (deduped)
- Fail closed: no user_message fabrication from list_dir for non-list goals

---

## 3. Turn type and budget decoupled from agent declaration

**Today:**
- Aviona `infer_interactive_max_steps(goal)` uses **keyword heuristics** on user text.
- `declared_turn_type()` runs **after** turn from decision log.
- Interactive loop uses single `max_steps` regardless of agent's first proposal.

**Problems:**
- `"write … show output"` matched `show` → 3 inspect steps (partially fixed by reordering).
- Agent never required to emit `turn_type` on cycle 1.
- Budget exceeded before multi-step edit+run completes.

**Replan should:**
- Cycle 1 proposal includes `turn_type` (or handoff).
- Python sets `max_steps`, `interactive_read_only`, permission profile from **declared type**, not regex on goal.
- Optional: agent may **revise** turn_type with handoff (inspect → edit promotion).

---

## 4. Working memory and tool output visibility

Architecture rule 5: truncate tool output before prompts.

**Symptom:** Model repeats identical tool calls despite prior success — suggests tool output not salient in next prompt, or model ignores reflection_guidance.

**Replan should:**
- Audit `WorkingMemoryBuilder` for interactive turns.
- Typed `ToolResultMessage` in decision log / working memory anchor section.
- Metrics in debug mode: was tool output present in prompt N+1?

---

## 5. Permission model vs inspect-run goals

`permissions.py`: default mode → side-effecting shell (`python`, `pytest`) → **ask** or **deny**.

**Symptom:** `type hello.txt` via shell denied; run/test prompts cannot complete without user `y` or `auto` mode.

**Replan should (framework policy, not Aviona hack):**
- Classify allow-listed read-only commands (`python -c …`, `pytest …`) for inspect turns when agent declared `turn_type:inspect` with run intent.
- Or: dedicated `tool_call` kind `run_tests` with sandbox (already have `run_tests` in executor for pytest tool?).

Check: executor has `pytest` tool via `run_tests` — agent may not know to use it instead of shell.

---

## 6. Tool surface mismatch

| Mentioned in Aviona hint | In executor |
|--------------------------|-------------|
| list_dir | yes |
| read_file | yes |
| code_edit | yes |
| shell | yes (permission gated) |
| glob | **no** |
| search_codebase | **no** (v2 plan mentioned) |

**Symptom:** `explore md files` → agent only has list_dir, loops.

**Replan should:** Add minimal glob/grep tools OR update skills so agent chains list_dir→read_file→terminate; document in executor skill YAML.

---

## 7. SELF_CHECK and quality gate interaction

**Fixed:** `terminate` allowed in interactive; varying keys include user_message, turn_type.

**Open:** Repeated `code_edit` triggers quality loop failure but doesn't force terminate path.

**Replan should:** Self-check issue type `must_terminate_after_edit` → cycle retry with structured issue, not unbounded code_edit.

---

## 8. Synthesis fallback philosophy

User explicitly rejected hardcoded completion. Remaining synthesis:
- From **last tool snapshot** (read_file, shell stdout)
- `"Updated {files}."` after code_edit

**Replan options (pick one in roadmap):**
- **A (strict):** Remove synthesis entirely → always `unresolvable` if no terminate.
- **B (framework):** Auto-terminate only when self-check passes and exactly one tool+edit pattern completed (typed, not goal regex).
- **C (agent):** Extra Decision Cycle role "finalizer" reads tool log → must emit terminate.

Document choice in roadmap phase.

---

## 9. Thesis eval track vs interactive track

Thesis phases 30–41 focus on **eval/ablation/SWE-bench** — batch runs, not REPL.

**Risk:** Fixing Aviona hides framework gaps needed for thesis **interactive** claims (if any).

**Replan should:** Add explicit **Framework Interactive Phases** (new numbers or 39a–39d) before resuming thesis table automation, OR merge into phase 41 E2E smoke.

---

## 10. Key files to modify (framework)

```
src/framework/orchestration/session.py   # _run_interactive_executor_turn
src/framework/control/cycle.py           # Decision Cycle, prompts
src/framework/control/self_check.py      # completion rules
src/framework/orchestration/executor.py  # tools, terminate dispatch
src/framework/memory/working_memory.py   # tool output in prompts
src/framework/control/models.py          # terminate payload, turn types
src/framework/error_control/quality.py   # loop detection policy
```

Aviona should shrink to: anchor, contract verify, permissions UI, render — **not** goal heuristics.
