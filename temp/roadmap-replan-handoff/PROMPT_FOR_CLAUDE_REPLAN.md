# Prompt for Claude — Replan Thesis + Aviona Roadmap

Copy everything below the line into Claude Opus (or similar). Attach the other files in `temp/roadmap-replan-handoff/`.

---

You are replanning a research codebase: **SLM Agentic Framework** (thesis) + **Aviona** (terminal REPL MVP for manual testing).

## Context

- **Thesis track:** Phases 0–38 DONE in code; **phase 39 paused** (thesis tables/LaTeX automation). Full thesis roadmap in repo `ROADMAP.md` + `ROADMAP_PHASES_NEXT.md` (phases 30–41).
- **Aviona v2 track:** Marked DONE (V2-0..V2-10, version 0.3.0) but **live REPL still has many failures** on real prompts outside the 9-case live gate.
- **Recent work (May 2026):** Removed `intent.py` phrase routing; added `--debug` logging; fixed some interactive-loop bugs; **removed all hardcoded Python shortcuts** per user request (no `python_complete`, no file aliases, no pre-turn disk reads).
- **User constraint:** Do **not** propose more custom/hardcoded/boilerplate code. Fix issues **structurally in the framework** first; keep Aviona thin.

## Your task

1. Read the attached handoff files (especially `PROBLEM_INVENTORY.md`, `FRAMEWORK_ROOT_CAUSES.md`, `FIXES_ALREADY_APPLIED.md`).
2. Produce a **new phased roadmap** that:
   - **Prioritizes framework (thesis) changes** that make interactive/conversational turns reliable.
   - Separates **Framework phases** from **Aviona product phases** (Aviona should mostly consume framework APIs).
   - Respects the 8 architecture rules in `ARCHITECTURE_RULES.md`.
   - Each phase has: Goal → Tasks → Acceptance tests → Commit message (same style as `ROADMAP.md`).
   - Avoids whack-a-mole: no regex routers, no fixture-specific handlers, no scraping tool output as the default user reply.
3. Address the **root cause** from `ROADMAP_PRODUCTION_AVIONA_V2.md` §1: thesis engine was a file-editing task runner; Aviona needs typed **user-visible outcomes** through the Decision Cycle, not post-hoc synthesis.
4. Propose how **turn type, budget, permissions, and completion** should work when:
   - The agent must use tools then **terminate** with `user_message`.
   - Goals are multi-step (read → answer, edit → verify → message, write test → pytest → show output).
   - Goals use context ("its content", "this code", prior turn references).
5. Include **eval/test strategy**: expand gates beyond 9 live prompts without brittle string matching.
6. Say explicitly what **not to build** (deleted patterns: intent routing, fallback scrape, auto-revert, hardcoded L3 handlers).
7. Output filenames:
   - `ROADMAP_FRAMEWORK_INTERACTIVE.md` — new thesis phases (insert before or after phase 39 — justify).
   - `ROADMAP_AVIONA_V3.md` — minimal product phases after framework is load-bearing (optional, short).
   - `PROGRESS_SEED.yaml` — suggested `current_phase` / `blocker` / phase log entries.

## Resolved facts (do not re-litigate)

- SLM never chooses workflow graph transitions (`next_state()` is Python).
- Every LLM call goes through Decision Cycle.
- Agents communicate via typed Pydantic messages only.
- `terminate{user_message, turn_type}` is the required completion kind.
- Aviona TurnContract verifies budget + writes + message presence.
- `glob` is mentioned in Aviona hints but **not implemented** in executor (bug).
- Default permission mode **asks** for side-effecting shell (`python`, `pytest`) — blocks run/test prompts in REPL unless auto mode or user confirms.

## Success criteria for the replan

A reader can implement phases in order and expect:
- REPL prompts like list/read/explore/edit/run-test either **terminate correctly** or **fail honestly** (`! reason`) — never a wrong tool dump marked `ok`.
- No new hardcoded phrase→action tables.
- Framework tests prove completion protocol; Aviona tests prove thin adapter + contract.

Deliver the roadmaps in markdown, ready to merge into the repo.
