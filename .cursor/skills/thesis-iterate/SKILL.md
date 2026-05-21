---
name: thesis-iterate
description: >-
  Drives phase-by-phase autonomous implementation of the SLM Agentic Framework
  thesis. Use when implementing thesis phases, reading PROGRESS.md/ROADMAP.md,
  running phase test gates, advancing phases, or debugging thesis framework code.
---

# Thesis Iterate

Autonomous, phase-by-phase implementation of the SLM Agentic Framework thesis.

**State files:** `PROGRESS.md` (current phase + `active_roadmap`), active roadmap file (see below), `ROADMAP.md` (thesis phases 0–41).

Project standards (code quality, testing, architecture) live in `.cursor/rules/thesis-roadmap.mdc`.

**Active roadmap resolution:** Read `active_roadmap` from `PROGRESS.md` CURRENT STATE. Examples:
- `framework-interactive-1` → `ROADMAP_FRAMEWORK_INTERACTIVE.md` § FI-1
- `thesis-39` → `ROADMAP.md` § Phase 39
- `AV3-1` → `ROADMAP_AVIONA_V3.md` § AV3-1

---

## Session protocol (run in order)

### Step 1 — Orient

Read `PROGRESS.md` and the **active roadmap** (from `active_roadmap` field) for the current phase section.

Determine: phase id, status (`NOT_STARTED` / `IN_PROGRESS` / `BLOCKED` / `DONE`), test gate, blockers.

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

Follow the active roadmap for the current phase only. Do not skip tasks or implement future phases.

Per file:

1. Read spec from the active roadmap
2. Read `thesis_solution_path_v4.md` in project root if present
3. Implement completely
4. Run unit tests for that file immediately

### Step 4 — Phase test gate

Run the gate from `PROGRESS.md` / active roadmap exactly, e.g.:

```bash
pytest tests/unit/test_X.py -v
```

On failure: fix implementation, re-run. Only change tests with justification in `PROGRESS.md`.

### Step 5 — Commit phase

```bash
git add -A
git status
git commit -m "FI-N: <message from ROADMAP_FRAMEWORK_INTERACTIVE.md>"
```

Use the active roadmap commit message verbatim (e.g. `FI-1: ...`, `phase-N: ...`, `AV3-1: ...`).

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
- All phases in the active roadmap Phase Overview are `DONE` → resume next track per `PROGRESS.md` (e.g. FI-7 → AV3-1; AV3-3 green → thesis-39)
- Blocker unresolved after 3 attempts

---

## File map

| Path | Role |
|------|------|
| `PROGRESS.md` | Current state + `active_roadmap` (agent updates) |
| `ROADMAP.md` | Thesis phase specs (0–41) |
| `ROADMAP_FRAMEWORK_INTERACTIVE.md` | FI-1..FI-7 ICP track (active) |
| `ROADMAP_AVIONA_V3.md` | AV3-1..AV3-5 product track (after FI-7) |
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
