---
name: thesis-handoff-report
description: >-
  Generates THESIS_PROJECT_HANDOFF_REPORT.md and PROMPT_EXTEND_ROADMAP.md when
  the final ROADMAP phase is DONE. Use when the last phase in ROADMAP.md
  completes, user asks for handoff for Claude Opus, extending the roadmap
  with new phases, or documenting implementation vs ROADMAP before the next sprint.
---

# Thesis Handoff Report

Produce a **concise, evidence-based** handoff for Claude (or another planner) to design **new phases after the current roadmap end**. Do not dump full file trees or every trace row into the report.

**Pair with:** `thesis-iterate` for implementation; this skill runs **once per milestone** when the **last phase listed in `ROADMAP.md`** is `DONE`.

---

## Resolve phase numbers (never hardcode)

From repo files each run:

| Symbol | How to obtain |
|--------|----------------|
| `last_roadmap_phase` | Highest phase number in `ROADMAP.md` **Phase Overview** (or last `## PHASE N` heading) |
| `current_phase` | `PROGRESS.md` → `current_phase` |
| `next_phase` | `last_roadmap_phase + 1` (first phase to add) |
| `completed_through` | All phases `0..last_roadmap_phase` with `status: DONE` in `PROGRESS.md` |

Use these values in prose and in generated prompts — **never** bake fixed phase ids into skill text.

---

## When to run

All must be true:

1. Every phase through `last_roadmap_phase` is `DONE` in `PROGRESS.md` (and `current_phase == last_roadmap_phase` with `phase_status: DONE`)
2. That phase's test gate from `ROADMAP.md` has passed
3. User wants external planning (Claude) or a project snapshot before extending the roadmap

If any phase ≤ `last_roadmap_phase` is not `DONE`, use `thesis-iterate` instead.

---

## Outputs (create/update only these)

| File | Purpose |
|------|---------|
| `THESIS_PROJECT_HANDOFF_REPORT.md` | Main snapshot for Claude |
| `PROMPT_EXTEND_ROADMAP.md` | Copy-paste prompt; must embed resolved `last_roadmap_phase` / `next_phase` |

Claude's deliverable filename: **`ROADMAP_PHASES_NEXT.md`** (user merges into `ROADMAP.md` after the last existing `## PHASE N` section).

**Do not create:** `_all_runs.json`, `PROJECT_FILE_TREE.txt`, `build_*.py`, or other scratch files.

---

## Workflow

### 1 — Orient

```text
Read PROGRESS.md  → current_phase, phase_status, phase log, known issues
Read ROADMAP.md   → Phase Overview, last ## PHASE N section, test gates
Compute last_roadmap_phase and next_phase
Run: git rev-parse --short HEAD && git tag -l
Run: pytest tests/unit/ -q && pytest tests/integration/ -q
```

### 2 — Per-phase code audit

For **each phase `0 .. last_roadmap_phase`**, read that phase's ROADMAP section + matching code/tests:

- Built modules and behaviors
- Deviations vs ROADMAP (numbered)
- Test gate and pass status

Split exploration across subagents by phase ranges if helpful; on failure, read code directly.

**Must capture** cross-cutting facts (provider, live session path vs LangGraph tests-only, ablation validity).

### 3 — Evaluation results

- Scan `traces/*.jsonl` aggregates only
- Best run per config A–D; canonical vs invalid runs
- Link `thesis_evaluation_report.md` for full history — do not duplicate all rows

### 4 — Write `THESIS_PROJECT_HANDOFF_REPORT.md`

Follow [reference.md](reference.md). In §4 title use **“Phase-by-phase (0–{last_roadmap_phase})”** with the resolved number.

§8: **~20 headlines for phases `{next_phase}` onward** — not fixed phase ids.

### 5 — Write `PROMPT_EXTEND_ROADMAP.md`

Regenerate each run with **resolved values**:

- Completed: phases `0..{last_roadmap_phase}`
- Append new specs starting at **Phase `{next_phase}`**
- Output file: `ROADMAP_PHASES_NEXT.md`
- After merge: set `PROGRESS.md` to `current_phase: {next_phase}`, `phase_status: NOT_STARTED`

### 6 — Commits (only if user asks)

```bash
git add .cursor/skills/thesis-handoff-report/ THESIS_PROJECT_HANDOFF_REPORT.md PROMPT_EXTEND_ROADMAP.md
git commit -m "docs: thesis handoff skill and snapshot for roadmap extension"
```

After user merges `ROADMAP_PHASES_NEXT.md`:

```bash
git add ROADMAP.md PROGRESS.md
git commit -m "progress: roadmap extended; advance to phase-{next_phase}"
```

Use literal `{next_phase}` only in the commit message after resolving the number.

---

## Quality bar

- Ground claims in `PROGRESS.md`, traces, or code
- No duplicate mega-trees or per-task dumps for every run
- LangGraph vs `session.py` documented accurately ([reference.md](reference.md))

---

## After handoff

1. User runs `PROMPT_EXTEND_ROADMAP.md` in Claude (thesis attached)
2. Merge `ROADMAP_PHASES_NEXT.md` into `ROADMAP.md`
3. Update `PROGRESS.md` for `next_phase`
4. Resume with `thesis-iterate`

---

## Additional resources

- [reference.md](reference.md) — template and glossary
- `.cursor/skills/thesis-iterate/SKILL.md` — implementation loop
