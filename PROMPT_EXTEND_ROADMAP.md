# Prompt: Extend ROADMAP — Phases 30+

Copy everything below into Claude Opus (attach this repo’s `ROADMAP.md`, `PROGRESS.md`, and `THESIS_PROJECT_HANDOFF_REPORT.md`).

---

## Context

You are extending the **SLM Agentic Framework** thesis implementation roadmap.

| Field | Value |
|-------|-------|
| **Completed phases** | `0` through **`29`** (all `DONE` in `PROGRESS.md`) |
| **Last roadmap phase** | **29** — Retrieval-mechanism ablation + Redis backend |
| **Next phase number** | **30** (first new section you write) |
| **Git at handoff** | `d0c28a5` (tag `v1.0-thesis-prototype`) |
| **Tests** | 160 unit passed (1 Redis skipped), 32 integration passed |

The implementing agent uses **Cursor** with `.cursor/skills/thesis-iterate/SKILL.md`. Each phase must include: Goal, Tasks (concrete paths), Acceptance tests (pytest or CLI), and exact commit message.

---

## What already exists (do not re-spec)

- Full framework: memory, control, error control, LangGraph **production** path (`engine=graph`), eval harness, ablation A–D, manifests, quality gate, decision JSONL, qualitative metrics, cost accounting, curated cite allowlist, repro bundle.
- **Canonical cited eval:** `humaneval_hard` n=10 seed=42 — A/B 90% SR, C/D 100% SR (`configs/cite_allowlist.yaml`).
- **Invalid run (never cite):** `D_humaneval_20260520T085222Z`.

Read `THESIS_PROJECT_HANDOFF_REPORT.md` §7–§8 for gaps and suggested headlines.

---

## Your deliverable

Produce **one file only:** `ROADMAP_PHASES_NEXT.md`

### Format rules

1. Start with `## PHASE 30 — <title>` — do **not** rewrite phases 0–29.
2. Continue with PHASE 31, 32, … as many as needed for a credible thesis completion sprint (aim for **8–15** full phases, not 20 thin stubs).
3. Each phase must follow the same structure as existing `ROADMAP.md` sections:
   - **Goal** (1–2 sentences, tie to RQ1/RQ2/RQ3 where relevant)
   - **Tasks** (bullet list with file paths)
   - **Acceptance tests** (Python test function names or CLI commands)
   - **Commit** (exact `git commit -m "phase-N: ..."` message)
4. Mark phases that need API budget, Docker, or committee decision with `[REQUIRES_USER_INPUT]` like the existing roadmap.
5. Include a short **Phase Overview** bullet list at the top of `ROADMAP_PHASES_NEXT.md` for phases 30+.
6. Add **test gate one-liners** at the end (like ROADMAP “One-Command Test Gates” section) for each new phase.
7. Prioritize in this order:
   - **Evidence** — live multi-seed ablation, curated allowlist updates, keyword vs semantic comparison
   - **Thesis writing** — automated tables/figures from curated runs only
   - **Remaining benchmarks** — MBPP, SWE-bench lite, agent-count (only if budget allows)
   - **Polish** — docs, CI smoke, optional Redis pilot

### Non-goals

- Do not propose rewriting the core architecture (pillars are fixed).
- Do not propose replacing LangGraph with a different orchestration library.
- Do not include phases that only duplicate existing DONE work without new acceptance tests.

### Architecture constraints (non-negotiable)

1. Agents pass state only through memory stores, not messages.
2. Agents communicate only via typed Pydantic messages.
3. SLM never decides workflow transitions — Python `next_state()` only.
4. Every LLM call goes through the Decision Cycle.
5. Write-guard at tool level; checkpoints atomic.

---

## After you finish

The user will:

1. Append `ROADMAP_PHASES_NEXT.md` sections to `ROADMAP.md` after `## PHASE 29`.
2. Update `PROGRESS.md`:
   ```yaml
   current_phase: 30
   phase_status: NOT_STARTED
   ```
3. Resume implementation with `thesis-iterate` in Cursor.

---

## Reference: phase 29 commit style

```
phase-29: retrieval-mechanism ablation (keyword vs semantic) + Redis backend (RQ1)
```

Use the same `phase-N: <short description>` pattern for all new phases.
