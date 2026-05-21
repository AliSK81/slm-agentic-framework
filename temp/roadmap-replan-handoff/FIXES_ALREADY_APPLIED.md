# Fixes Already Applied (Do Not Re-Propose)

Commits on `master` through `4f3bc76` (2026-05-21).

---

## Aviona v2 baseline (pre-debug sprint)

| Commit | Summary |
|--------|---------|
| `838f43a` | L3 live gate (9 locked prompts) |
| `76ea3a2` | Runtime anchor for meta/self questions |
| `be8b979` | v2-4: delete regex/fallback/scrape stack |
| `9f61b4f` | Per-turn-type budgets + read-only enforcement |
| `3057273` | v2-10 docs, version 0.3.0 |

---

## Debug + interactive hardening sprint

| Commit | Summary |
|--------|---------|
| `866f0cf` | `--debug` tracing; remove `intent.py`; agent-only REPL; interactive loop fixes; `debug_session.py`; faster startup (no API probe in REPL) |
| `10c80eb` | Remove all hardcoded inspect shortcuts (`python_complete`, aliases, greet run, pre-turn disk reads, tool auto-returns) |
| `4f3bc76` | PROGRESS last_commit chore |

---

## Framework changes in sprint (by area)

### `src/framework/orchestration/session.py`
- Interactive loop with terminate handling
- `read_tools_used` dedup (`tool:path` keys)
- `code_edits_done` dedup for repeat edits
- `last_tool_snapshot` for synthesis from agent tool results only
- Removed: `_try_python_inspect_complete`, `_try_run_code_output`, file aliases, list_dir auto-complete

### `src/framework/control/self_check.py`
- Allow executor `terminate` in interactive mode
- Varying keys: user_message, turn_type, reason (cross-turn contradiction fix)
- Skip contradiction checks for tool_call kind

### `src/framework/control/cycle.py`
- Debug tracing; decision_floor; format hints for terminate

### `src/framework/orchestration/executor.py`
- Tool aliases (exec→shell); tracing; read_file path resolution

### `src/framework/tools/file_tools.py`
- Absolute path resolve under workspace

### `src/aviona/`
- `debug_log.py`, `--debug` in cli/repl/session
- Conditional `runtime_answer_constraint()` for answer-only goals
- `interactive_turn_contract_hint()`

---

## Tests added/updated

- `tests/unit/test_aviona_debug.py`
- `tests/integration/test_interactive_turn.py` (explore no listing fallback, empty file synthesis)
- `tests/unit/test_runtime_answer.py` (infer_interactive_max_steps)
- Deleted `tests/unit/test_aviona_intent.py`

---

## Known regressions after removing hardcode

| Before (hardcoded) | After (agent-only) |
|--------------------|-------------------|
| 0 steps list/read/main/run | 1–3+ LLM steps, may fail |
| Instant correct answers | Depends on DeepSeek-v4-flash behavior |
| 9/11 debug_session with 0-step cases | Live API flaky on inspect/edit |

**User explicitly chose agent-only over hardcode.**

---

## Debug log examples (on user's machine)

```
C:\Users\alieb\.aviona\debug\418ec76bb16043f092f28ea7b1b24614.txt  # session with explore/edit issues
C:\Users\alieb\.aviona\debug\a28c4fad1411455baadcdd784fc2e58c.txt  # extended manual session
C:\Users\alieb\.aviona\debug\e50eab3a6dbe4d92a141c9f305859f32.txt  # 8/8 pass with hardcode
```

Logs not copied into repo (user-local). Patterns documented in `SESSION_EVIDENCE.md`.
