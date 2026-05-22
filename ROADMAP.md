# ROADMAP — Thesis phases (index)

> Phases **0–38 DONE**. **39–41 PAUSED.** Active work: **FW-5** in `PROGRESS.md`.  
> Full phase specs (tasks, tests, commits) are in git history before 2026-05-22 if needed.

## Architecture

Memory (4 stores + WM) · Control (Decision Cycle + LangGraph FSM) · Error control (9 mechanisms) · Planner + Executor agents · Provider-agnostic SLM client.

## Phase index

| Phase | Topic | Status |
|-------|-------|--------|
| 0 | Bootstrap | DONE |
| 1 | SLM client | DONE |
| 2 | Memory stores | DONE |
| 3 | Working memory builder | DONE |
| 4 | Error control | DONE |
| 5 | Tools | DONE |
| 6 | Decision cycle | DONE |
| 7 | Workflow FSM | DONE |
| 8 | Agents | DONE |
| 9 | Full session E2E | DONE |
| 10 | Eval harness | DONE |
| 11 | Ablation A–D | DONE |
| 12 | Trace analysis | DONE |
| 13 | Run quality gate | DONE |
| 14 | Manifest + `--task-id` | DONE |
| 15 | Difficulty slices | DONE |
| 16 | Multi-step scenarios | DONE |
| 17 | Reflection on REVISE | DONE |
| 18 | True-SLM profiles | DONE |
| 19 | Multi-seed ablation | DONE |
| 20 | MBPP ablation | DONE |
| 21 | SWE-bench Docker | DONE |
| 22 | Agent-count experiment | DONE |
| 23 | Decision JSONL | DONE |
| 24 | Qualitative metrics | DONE |
| 25 | LangGraph production | DONE |
| 26 | Cost accounting | DONE |
| 27 | Curated report + repro | DONE |
| 28 | Hardening | DONE |
| 29 | Semantic retrieval + Redis | DONE |
| 30 | Discriminative slice | DONE |
| 31–37 | Live benchmark matrices | DONE (structural; live deferred) |
| 38 | Failure taxonomy | DONE |
| 39 | LaTeX tables/figures | PAUSED |
| 40 | Repro bundle | PAUSED |
| 41 | E2E regression smoke | PAUSED |

## Satellite tracks (all DONE)

Aviona v1 (1–12) · Aviona v2 (V2-0..10, 0.3.0) · Framework ICP (FI-1..7) · Aviona v3 (AV3-1..5, 0.4.0) · Ablation fix FW-1..4.
