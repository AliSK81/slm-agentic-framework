# Agent session bootstrap

## Every new session (in order)

1. **Read `PROGRESS.md`** — `current_phase`, `phase_status`, `active_roadmap`, `blocker`, `background_report`
2. **Read the active roadmap** file named in `active_roadmap` (current section only)
3. For codebase architecture questions: use **`graphify-out/GRAPH_REPORT.md`** as the knowledge-graph entry point
4. Apply **`.cursor/skills/thesis-iterate/`** when implementing roadmap phases

## Current active work (as of 2026-05-22)

| Field | Value |
|-------|--------|
| Phase | **FW-1** (`NOT_STARTED`) |
| Roadmap | `ROADMAP_FRAMEWORK_ABLATION_FIX.md` |
| Why | E2E ablation: config D (70% SR) < A (80% SR) on `humaneval_hard` with `qwen2.5-coder:3b` |
| Evidence | `reports/framework_investigation_20260522_qwen25coder3b.md` |

**Do not** resume Aviona v3 or thesis phase 39 until FW-1..FW-5 complete (or user redirects).

## Rules

- Implement **only** the current roadmap phase; run its test gate before advancing
- Only read raw source files when implementing or when the user explicitly asks
- Query the knowledge graph for exploration; `graphify-out/GRAPH_REPORT.md` is the entry point
