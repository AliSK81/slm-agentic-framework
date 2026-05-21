# Problem Inventory — Framework vs Aviona

**Legend:** Fixed | Partial | Open | Removed (was hardcoded, now agent-only)

**Priority for replan:** Framework (F) > Aviona adapter (A) > Test harness (T)

---

## A. Reported in user REPL sessions (real API, `aviona --debug`)

| ID | Scenario | Bad outcome observed | Layer | Status |
|----|----------|----------------------|-------|--------|
| R01 | Slow REPL startup (multi-second before prompt) | API probe at startup | A | **Fixed** — local key check only |
| R02 | `just say "ali ali"` then `tell me what is your llm model?` | Stuck / SELF_CHECK contradiction | F | **Partial** — cross-turn retry keys fixed |
| R03 | `tell me the model you are` | Worked after fixes | F | **Fixed** (mostly) |
| R04 | `what question i just asked you?` | Needs history; worked once | F | **Open** — context-dependent |
| R05 | `list files in current dir` (repeat) | 3 steps, ~13–17s each time | F+A | **Open** — agent loops list_dir, no terminate |
| R06 | `what is content of main file?` | Directory listing as answer | F | **Open** — agent list_dir×3, synthesis was listing |
| R07 | `what is content of hello file?` | list_dir loop → missing user_message | F | **Partial** — live flaky |
| R08 | `what is the content of solution.py?` (empty) | missing user_message | F | **Partial** — synthesis from tool snapshot if read_file ran |
| R09 | `read notes.txt` | Was 0-step hardcode; now agent | F | **Removed hardcode** — agent path, slower |
| R10 | `explore md files` | Directory listing marked ok | F | **Partial** — bad fallback removed; still fails or wrong |
| R11 | `can you read first 3 lines of bar.txt?` | Full file content, not 3 lines | F | **Open** — agent doesn't slice; no terminate shaping |
| R12 | `edit bar.txt and put a random sentence` | 6 steps; `"Updated bar.txt."` not real sentence | F | **Partial** — edit applies; synthesis not terminate |
| R13 | `read its content now` (after edit) | Slow; anaphora | F | **Partial** — worked once with agent |
| R14 | `run this code with input "ali ebrahimi"…` | Directory listing | F | **Open** — needs shell+terminate; model lists dir |
| R15 | `write a unit test… run it… show output` | Directory listing; budget was 3 (show token) | F+A | **Partial** — budget order fixed; agent still lists dir |
| R16 | `hi` → `"Hi there!"` | Live test wanted substring `hi` | T | **Partial** — harness strictness |
| R17 | `try to fastly reply with "salam"` | Worked | F | **Fixed** (mostly) |

---

## B. Framework structural issues (thesis — fix in replan)

| ID | Issue | Why it matters | Status |
|----|-------|----------------|--------|
| F01 | **Completion gap:** agent runs tools but omits `terminate{user_message}` | #1 cause of `missing user_message` | **Open** |
| F02 | **Synthesis fallback** from tool snapshot when terminate missing | Band-aid; user rejects hardcode | **Partial** — only post-tool, no phrase routing |
| F03 | **max_steps inferred in Aviona** via keyword heuristics (`show`, `write`, …) | Wrong budget for compound goals | **Partial** — ordering fixed, still heuristic |
| F04 | **Turn type declared after turn** from decisions, not driving interactive loop | Budget/permissions not aligned with agent declare | **Open** |
| F05 | **Interactive loop** separate from full graph; reflection_guidance string injection | Ad-hoc; not typed messages | **Open** |
| F06 | **Repeat tool loops** (list_dir, code_edit) | Burns budget; quality gate loops on edit | **Partial** — read_tool_key dedup |
| F07 | **SELF_CHECK** contradiction across turns | Fixed varying keys; meta vs prior answer | **Partial** |
| F08 | **Working memory** may not surface tool output clearly for next cycle | Model repeats same tool | **Open** |
| F09 | **Executor terminate** was blocked for planner-only kinds | Broke interactive answer | **Fixed** |
| F10 | **`glob` in prompt hint, not in executor** | Misleading agent | **Open** |
| F11 | **Shell/pytest permission** default mode = ask/deny | Blocks run/test inspect goals | **Open** (A permissions + F tool policy) |
| F12 | **Inspect budget = 3** too tight for list→read→terminate | Systematic budget exceeded | **Open** |
| F13 | **Edit budget = 6** tight for read→edit→terminate | edit-bar used all 6 | **Open** |
| F14 | **No typed "tool_result → summarize → terminate" protocol** in Decision Cycle | Python uses free-text reflection_guidance | **Open** |
| F15 | **SessionOutcome.user_message** populated outside terminate path | Contract drift | **Open** |
| F16 | **Quality gate loop detection** on repeated code_edit | Good but agent never pivots to terminate | **Partial** |
| F17 | **read_file absolute paths** outside workspace | Was broken | **Fixed** in file_tools |
| F18 | **Anchor + AVIONA.md project rules** bias smoke examples | Wrong edits on casual prompts | **Open** |
| F19 | **Multi-step goals** (write+run+show) span inspect+edit+shell | Single turn_type/budget inadequate | **Open** |
| F20 | **Anaphora / multi-turn references** ("it", "this code") | No framework reference resolution | **Open** |

---

## C. Aviona product / MVP issues (keep thin after framework fix)

| ID | Issue | Status |
|----|-------|--------|
| A01 | Deleted `intent.py` — all lines through agent | **Done** |
| A02 | `--debug` log to `~/.aviona/debug/*.txt` | **Done** |
| A03 | TurnContract + budgets.py caps | **Done** — may need framework-driven budgets |
| A04 | `infer_interactive_max_steps()` keyword heuristics | **Open** — should move to framework or agent declare |
| A05 | `runtime_answer_constraint()` only on answer-only goals | **Done** |
| A06 | render.py `!` prefix on contract fail | **Done** |
| A07 | L3 live gate only 9 prompts | **Open** — coverage gap |
| A08 | debug_session.py 9 prompts | **Open** — removed hardcode-dependent cases |
| A09 | Permission REPL confirm for shell in default mode | **Open** — UX |
| A10 | Install `-e .` required to pick up changes | **Ops** |

---

## D. Removed anti-patterns (do NOT reintroduce in replan)

| Pattern | Why removed |
|---------|-------------|
| `intent.py` phrase → local handler | User rejected |
| `_try_python_inspect_complete()` 0-step answers | Hardcoded bypass |
| File aliases (`main file` → main.py) | Fixture-specific |
| `_try_run_code_output()` greet via python -c | Fixture-specific |
| Pre-turn disk read from goal text | Hardcoded |
| Auto-return after list_dir/read_file without terminate | Wrong ok answers |
| Generic fallback: any tool output → user_message | explore/unit-test got listings |
| `effects.py`, `fallbacks.py`, scrape stack (v2-4) | Architectural debt |

---

## E. Automated test coverage vs user reality

| Covered (L3 live) | Not covered (user sessions) |
|-------------------|----------------------------|
| hi, ok, model, salam | explore md files |
| hello content, project, list files | main file / anaphora |
| create foo.txt | edit + read chain |
| | run code with input |
| | unit test + pytest + output |
| | partial line read |
| | repeat list (latency) |
| | shell permission flow |

See `TEST_COVERAGE_GAPS.md` for full matrix.

---

## F. Suggested framework-first fix themes (for planner)

1. **Interactive Completion Protocol (ICP)** — after tool success, Decision Cycle enters mandatory terminate sub-step (typed, not string guidance).
2. **Agent-declared turn_type on cycle 1** drives budget + read_only + permissions (Python enforces).
3. **Tool result channel** — truncated tool output in working memory as typed block, not reflection_guidance hack.
4. **Compound turn support** — either multi-phase turn types or explicit sub-turn state machine (inspect→edit→inspect).
5. **Permission policy** for inspect-run (pytest/python read-only classify or auto-allow in workspace).
6. **Executor tool parity** — implement glob/search or remove from hints.
7. **Honest failure** — no synthesis except optional edit confirmation from verified writes (user decision).
