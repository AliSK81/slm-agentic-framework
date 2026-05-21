# Test Coverage Gaps

---

## L2 — Mocked (no API)

| Suite | Path | What it proves |
|-------|------|----------------|
| Contract matrix | `tests/unit/test_aviona_contract_matrix.py` | TurnContract rules in isolation |
| Aviona unit | `tests/unit/test_aviona_*.py` | ~91 tests via `test-aviona.ps1` |
| Interactive integration | `tests/integration/test_interactive_turn.py` | Mock SLM interactive loop |
| Framework unit | `tests/unit/test_self_check.py`, etc. | Cycle, self_check, quality |

**Gap:** Mocks often queue `terminate` immediately — does not reproduce list_dir loops.

---

## L3 — Live API (`scripts/live_gate.py`)

| ID | Prompt | turn_type |
|----|--------|-----------|
| answer-hi | hi | answer |
| answer-ok | ok | answer |
| answer-model | what is your model? | answer |
| answer-language-model | what language model? | answer |
| answer-salam | try to fastly reply with "salam" | answer |
| inspect-hello-content | what is content of hello file? | inspect |
| inspect-project | what is this project | inspect |
| inspect-list-files | list files in this dir | inspect |
| edit-create-foo | create foo.txt with "x" | edit |

**Not in L3 (user reported failures):**

- explore md files
- content of main file / solution.py (empty)
- read notes.txt / partial lines
- edit bar.txt + read its content
- run code with input
- write unit test + run + show output
- what question did I ask (meta-history)
- repeat list files (latency)

---

## Debug session (`scripts/debug_session.py`)

9 cases in one session (after hardcode removal):

1. greeting-echo, meta-model, meta-gpt, meta-hi
2. inspect-hello, inspect-list, inspect-explain, inspect-empty
3. edit-bar

**Removed from matrix:** inspect-main, run-greet (were 0-step hardcode cases)

---

## Framework tests missing (suggested for replan)

| Test | Purpose |
|------|---------|
| `test_interactive_must_terminate_after_read_file` | Mock read without terminate → expect fail or typed auto-finalize |
| `test_list_dir_repeat_blocked_then_terminate` | Dedup + completion |
| `test_compound_edit_run_budget` | write+pytest gets edit budget not inspect |
| `test_shell_inspect_permission_policy` | Framework policy for pytest tool |
| `test_no_synthesis_from_list_dir_for_explore_goal` | Already have explore test |
| `test_working_memory_contains_tool_output` | Prompt inspection |
| E2E REPL matrix | Subprocess like live_gate but 20+ cases |

---

## CI vs local

- Full suite: `pytest -m "not e2e"` (~380 tests)
- E2E real API: `@pytest.mark.e2e` — not in default CI
- Live gate: manual / `-Live` flag

**Replan should:** Define which interactive tests are CI-mocked vs nightly-live.

---

## Acceptance criteria philosophy (user request)

- Contract-based: turn_type, budget, writes, non-empty message
- **Not** substring journey regex (deleted in v2-6)
- Live must_contain for content checks is OK at **harness layer** only — not routing
