# Task: Plan **Aviona** — production roadmap (Claude Code–minimal)

You are planning the next implementation sprint for an existing codebase. **Do not implement code in this turn.** Produce **one markdown file only:** `ROADMAP_PRODUCTION_AVIONA.md`.

---

## Attachments you already have

Use these files as ground truth (do not invent paths):

| Attachment | Role |
|------------|------|
| `AVIONA_UX_SPEC.md` | **Primary UX contract** — read first |
| `THESIS_PROJECT_HANDOFF_REPORT.md` | What exists; thesis phases 0–38 done, 39–41 paused |
| `PROGRESS.md` | Phase log; live benchmarks deferred by author |
| `src/framework/orchestration/session.py` | `run_full_session(engine="graph"\|"loop")`, `SessionOutcome`, graph + SqliteSaver |
| `src/framework/control/cycle.py` | `DecisionCycle` — READ → PROPOSE → SELF_CHECK → CORRECT → ACT → RECORD |
| `src/framework/tools/` | `file_tools.py`, `search.py`, `test_runner.py`, `compile_check.py`, … |
| `configs/models.yaml` | Model profiles, timeouts, `price_per_1k_*`, working-memory caps |

**There is no** `decision_cycle.py`. The cycle lives in **`cycle.py`**.

Optional if also attached: `ROADMAP.md` (thesis phases 0–41 — **reference only, do not rewrite**), `pyproject.toml` (no console script yet).

---

## Product in one sentence

**Aviona** = the user runs `aviona` inside a project directory and gets a **Claude Code–style terminal session**: conversational prompts, agent **gathers context → acts → verifies** in a loop, **files scoped to cwd**, session persisted locally — powered by the **existing** thesis engine, **not** by `eval/run_eval.py`.

Full UX detail is in `AVIONA_UX_SPEC.md`. Your roadmap must implement that spec, not a generic batch CLI.

---

## Authoritative product requirements

### 1. Session UX (like Claude Code)

```text
cd D:\my-project
aviona
```

- **cwd** = workspace root; all file tools **jail** to this tree (extend write-guard).
- **REPL / chat loop** in the terminal — user types prompts; can **interrupt** and steer without starting a new “benchmark task”.
- **Session persistence** under `~/.aviona/projects/` (conversation + metadata); design resume for a later phase.
- **Project rules file** at session start (like `CLAUDE.md`) — propose final name in roadmap (`AVIONA.md` vs `.aviona/PROJECT.md`).
- **Checkpoints before edits** — wire existing `framework.memory.checkpoint`; expose undo in UX (`aviona undo` or keybinding doc).

### 2. Agentic loop — reuse, do not replace

Map Claude Code’s loop to **existing** code:

| Claude Code phase | Use in Aviona |
|-------------------|---------------|
| Gather context | `DecisionCycle` READ_CONTEXT + `search` / `read_file` + load `AVIONA.md` |
| Take action | ACT + `file_tools` + guarded shell/pytest |
| Verify | Re-run tests / compile; graph `EVALUATE` where applicable |

- **Entry point for work:** `run_full_session()` in `session.py` with `engine="graph"` (default production path).
- **Do not** build a second parallel agent stack.
- **Do not** use HuggingFace / `eval.datasets` in the main Aviona loop.

### 3. Efficiency (high priority)

Plan phases **before** heavy polish features:

- Reduce **output tokens** (executor/planner replies, self-check, user-visible status).
- Tune **tool output truncation** and working-memory ceiling (`configs/models.yaml`, error_control).
- **Compaction policy** when context fills (truncate old tool blobs first, then summarize).
- Measure with **`TrackingSLMClient`** / per-step usage — **no** mandatory live benchmark matrix in this track.
- Windows-friendly **`pip install -e .`** and **`aviona` on PATH**.

### 4. Install & dev mode

- Editable install picks up framework changes without reinstall friction.
- Secrets in `%USERPROFILE%\.aviona\` (or `.env` loaded at startup) — **never** committed.
- Optional: `aviona doctor` — API probe only (reuse `validate_slm_api_key` pattern from `session.py`).

### 5. Thesis — separate track, last, blocked

- **`eval/`** stays for thesis benchmarks and cite allowlist.
- Phases **39–41** in `ROADMAP.md` (LaTeX, repro zip, e2e smoke) → short **“Thesis resume”** section at end of your file, every item `[REQUIRES_USER_INPUT]`.
- **No** planning that requires spending API tokens on 12-run discriminative ablations **now**.

---

## Architecture rules (non-negotiable)

From the thesis framework — Aviona must comply:

1. State only through **memory stores**, not free-text message passing between agents.
2. Agents communicate via **typed Pydantic messages** only.
3. **SLM never** chooses workflow transitions — Python / graph only.
4. Every LLM call goes through the **Decision Cycle**.
5. **Truncate** tool output before prompts.
6. **Anchor** (goal + constraints) first in every prompt.
7. **Decision log** append-only.
8. **Write-guard** at tool level.

---

## Map to attached code (use in phase tasks)

When writing tasks, cite **real paths**:

| Concern | Path |
|---------|------|
| Session / graph | `src/framework/orchestration/session.py`, `src/framework/orchestration/graph.py` (if present) |
| Decision Cycle | `src/framework/control/cycle.py` |
| Tools | `src/framework/tools/file_tools.py`, `search.py`, `test_runner.py` |
| Truncation / parser | `src/framework/error_control/` |
| Memory / checkpoint | `src/framework/memory/` |
| SLM + usage | `src/framework/slm/` |
| Config | `configs/models.yaml` |
| **New package entry** | propose `src/aviona/` or `src/framework/cli/` + `pyproject.toml` `[project.scripts]` |

Current `pyproject.toml` has **no** `[project.scripts]` — Aviona phases must add `aviona = ...`.

---

## Deliverable: `ROADMAP_PRODUCTION_AVIONA.md`

### Structure

1. **Introduction** (½ page) — product vision, relation to thesis, what v1 ships.
2. **Architecture diagram** (ASCII or mermaid) — user → `aviona` REPL → session driver → `run_full_session(graph)` → cycle + tools.
3. **Phases `AVIONA-1` … `AVIONA-N`** — aim for **10–14** phases, ordered:
   - Early: packaging + REPL + cwd jail + `AVIONA.md`
   - Early: output-token / truncation / compaction efficiency
   - Mid: permissions, checkpoints/undo, session JSONL
   - Late: `doctor`, resume/fork (optional)
   - **Last section:** `THESIS-RESUME-1` … (39–41 + live benchmarks), all `[REQUIRES_USER_INPUT]`
4. **Open decisions** — REPL library, package layout (`aviona` vs extend `slm-agentic-framework`), multi-turn vs one graph run per user line.

### Each phase must include

```markdown
## AVIONA PHASE N — <title>

**Goal:** …

### Tasks
- `path/to/file.py` — concrete change
- …

### Acceptance tests
\`\`\`bash
pytest tests/unit/test_….py -v
# and/or CLI with --dry-run where possible
\`\`\`

### Commit
\`\`\`
git commit -m "aviona-N: <short description>"
\`\`\`
```

- Prefer **unit tests with mocks** — no live API in Aviona track unless marked `[REQUIRES_USER_INPUT]`.
- Implementing agent will use `.cursor/skills/thesis-iterate/SKILL.md` — match its tone (gates, exact commit messages).

### v1 definition of done (must be explicit in roadmap)

After phases through **AVIONA-K** (you pick K), a user can:

```bash
pip install -e .
cd <any small repo>
aviona
> create hello.txt with "hi"
# file exists under cwd; session log under ~/.aviona/
```

Without running `python -m eval.run_eval`.

---

## Anti-patterns (reject in your plan)

- Main command `aviona run "single shot"` with no interactive session.
- Duplicating Decision Cycle or LangGraph wiring in a greenfield `agent.py`.
- Making `eval/scenarios/ablation.py` the product entry point.
- Mandatory live DeepSeek/OpenRouter benchmark matrices in Aviona phases.
- Rewriting or merging thesis `ROADMAP.md` phases 0–41 into Aviona phases.

---

## Output rules

- Return **only** the full contents of `ROADMAP_PRODUCTION_AVIONA.md`.
- No preamble, no implementation, no other files.
- Phase names must start with `AVIONA` (thesis resume phases may use `THESIS-RESUME`).

---

## After the author approves your roadmap

They will implement in Cursor, update `PROGRESS.md` with `current_track: aviona`, and run phases with tests — not thesis phase 39 until they explicitly restart the benchmark track.
