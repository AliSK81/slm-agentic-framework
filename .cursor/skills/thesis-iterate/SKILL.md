---
name: thesis-iterate
description: >-
  Drives phase-by-phase autonomous implementation of the SLM Agentic Framework
  thesis. Use when implementing thesis phases, reading PROGRESS.md/ROADMAP.md,
  running phase test gates, advancing phases, or debugging thesis framework code.
---

# Thesis Iterate

Autonomous, phase-by-phase implementation of the SLM Agentic Framework thesis.

**State files:** `PROGRESS.md` (current phase), `ROADMAP.md` (specs and test gates).

Project standards (code quality, testing, architecture) live in `.cursor/rules/thesis-roadmap.mdc`.

---

## Session protocol (run in order)

### Step 1 — Orient

Read `PROGRESS.md` and `ROADMAP.md` (current phase section).

Determine: phase number, status (`NOT_STARTED` / `IN_PROGRESS` / `BLOCKED` / `DONE`), test gate, blockers.

If `BLOCKED` → resolve, document in `PROGRESS.md`, continue.

### Step 2 — Verify environment

```bash
python --version                    # >= 3.11
# venv active; .env exists (user fills keys)
source .venv/bin/activate 2>/dev/null || .venv\Scripts\activate
```

If no venv:

```bash
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Step 3 — Implement current phase

Follow `ROADMAP.md` for the current phase only. Do not skip tasks or implement future phases.

Per file:

1. Read spec from `ROADMAP.md`
2. Read `thesis_solution_path_v4.md` in project root if present
3. Implement completely
4. Run unit tests for that file immediately

### Step 4 — Phase test gate

Run the gate from `PROGRESS.md` / `ROADMAP.md` exactly, e.g.:

```bash
pytest tests/unit/test_X.py -v
```

On failure: fix implementation, re-run. Only change tests with justification in `PROGRESS.md`.

### Step 5 — Commit phase

```bash
git add -A
git status
git commit -m "phase-N: <message from ROADMAP.md>"
```

Use the ROADMAP commit message verbatim.

### Step 6 — Update PROGRESS.md

- Set completed phase `DONE` + commit hash (`git rev-parse --short HEAD`)
- Increment `current_phase`, set `phase_status: NOT_STARTED`, clear `blocker`

```bash
git add PROGRESS.md
git commit -m "progress: phase-N complete, advancing to phase-N+1"
```

### Step 7 — Continue

Proceed to the next phase without stopping.

**Stop only when:**

- Phase has `[REQUIRES_USER_INPUT]` and prerequisite is unmet
- All phases in `ROADMAP.md` Phase Overview are `DONE` → then run **`thesis-handoff-report`** skill for Claude/next-phase planning
- Blocker unresolved after 3 attempts

---

## File map

| Path | Role |
|------|------|
| `ROADMAP.md` | Phase specs and test gates |
| `PROGRESS.md` | Current state (agent updates) |
| `configs/models.yaml` | Model profiles |
| `configs/memory.yaml` | Memory / retrieval weights |
| `configs/eval.yaml` | Benchmark / ablation config |
| `.env` | Secrets (never commit) |
| `src/framework/slm/` | OpenRouter client, skill cards |
| `src/framework/memory/` | Stores, retrieval, reflection, checkpoint |
| `src/framework/control/` | Decision Cycle, SELF_CHECK, workflow, ledger |
| `src/framework/orchestration/` | Planner, Executor, messages, graph |
| `src/framework/tools/` | Tests, compile, file tools, search |
| `src/framework/error_control/` | Parser, quality, truncation, watchdog, sandbox |
| `eval/` | Datasets, metrics, ablation |
| `tests/unit/` | Fast, mocked |
| `tests/integration/` | SQLite in-memory, mocked SLM |
| `tests/e2e/` | Real API (`@pytest.mark.e2e`) |

---

## Architecture quick reference

See [reference.md](reference.md) for failure-pattern fixes and detailed architecture tables.

**Modules → RQs:** Memory (L1+L2) → RQ1; Control (cycle + FSM) → RQ2+RQ3; Error control (9 mechanisms) → RQ3.

**Decision Cycle:** `READ_CONTEXT → PROPOSE → SELF_CHECK → CORRECT → ACT → RECORD` (max 3 retries on self-check fail).

**Workflow:** `PLAN → DISPATCH → EXECUTE → EVALUATE → DONE` with `REVISE` / `ESCALATE` on failure.

**Ablation:** A (none), B (memory), C (control), D (full).
