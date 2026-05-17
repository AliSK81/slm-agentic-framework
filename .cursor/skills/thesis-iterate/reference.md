# Thesis Iterate — Reference

## Common failure patterns

### ImportError: cannot import name X from framework

Check `__init__.py` exports, e.g. `src/framework/memory/__init__.py` must export the symbol.

### pydantic ValidationError on DecisionEntry

- `rationale` not empty
- `kind` matches Literal exactly
- `by_agent` is `"planner"` or `"executor"` (lowercase)
- `self_check` is `SelfCheckRecord`, not a dict

### LangGraph StateGraph compile error

- Node return dict must match `WorkflowState` fields
- Conditional edge labels must exist in edge map
- `entry_point` set before `compile()`

### pytest collects 0 tests

- Files/functions must start with `test_`
- `conftest.py` in `tests/`; `testpaths` in `pyproject.toml`

### OpenRouter 401

- `.env` has `OPENROUTER_API_KEY=sk-or-...`
- `load_dotenv()` before reading env in `client.py`
- Header: `Bearer {key}`

### SQLite disk I/O error

```bash
mkdir -p data/
```

Check `SQLITE_PATH` in `.env` is writable.

### Phase 9 E2E: session reaches ESCALATE not DONE

Often model capability on hard tasks:

1. Confirm synthetic tasks (not full HumanEval)
2. Inspect Decision Log — did Executor attempt code?
3. If retries exhausted: verify goal+constraints in Executor prompt (WorkingMemoryBuilder anchor)
4. If tools fail: check `WORKSPACE_ROOT` exists and is writable

---

## Architecture detail

### Three modules → three RQs

| Module | What it does | Answers |
|--------|--------------|---------|
| Memory | L1 Working Memory (≤900 tokens) + L2 (4 stores, SQLite) | RQ1 |
| Control Logic | Decision Cycle + Workflow FSM | RQ2 + RQ3 |
| Error Control | 9 deterministic mechanisms, no LLM | RQ3 |

### Self-check (3 checks)

1. Schema validation (Pydantic)
2. Contradiction with last 10 Decision Log entries
3. Scope violation (Executor planning, Planner calling tools)

### Retrieval scoring (Generative Agents, 2023)

```
score = 0.2 × recency + 0.5 × importance + 0.3 × keyword_overlap
recency = 0.995 ^ hours_since_last_access
importance ∈ {0.5, 1.0}
```

### Ablation configs

| Config | Memory | Control | Error control |
|--------|--------|---------|---------------|
| A | No | No | No |
| B | Yes | No | No |
| C | No | Yes | No |
| D | Yes | Yes | Yes |
