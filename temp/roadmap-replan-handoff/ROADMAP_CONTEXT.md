# Roadmap Context

---

## Active tracks (PROGRESS.md)

```yaml
current_phase: thesis-39
phase_status: PAUSED
thesis_track: paused_at_phase_39
aviona_track: v2
aviona_v2_status: DONE   # V2-10 complete — but REPL still flaky
active_roadmap: ROADMAP_PRODUCTION_AVIONA_V2.md
last_commit: "10c80eb"   # framework no-hardcode (PROGRESS may say 4f3bc76 chore)
blocker: null
```

---

## Thesis roadmap files

| File | Scope |
|------|-------|
| `ROADMAP.md` | Phases 0–29 DONE; 30–41 in appendix / continuation |
| `ROADMAP_PHASES_NEXT.md` | Phases 30–41 spec (eval, ablation, thesis tables, docs) |
| Phase 39 (paused) | Thesis tables & figures automation (LaTeX, curated runs only) |
| Phase 40–41 | Docs, reproducibility zip, E2E smoke |

**Thesis work is eval/ablation/evidence heavy** — does not address interactive REPL completion.

---

## Aviona roadmap

| File | Scope |
|------|-------|
| `ROADMAP_PRODUCTION_AVIONA_V2.md` | v2 architectural replan (DONE in PROGRESS) |
| `ROADMAP_PRODUCTION_AVIONA.md` | v1 frozen |

**v2 executive summary (still valid):** Root cause = task-runner engine bolted to conversational REPL; fix = typed `user_message`, agent-declared turn types, TurnContract, delete scrape/fallback.

**Gap:** v2 implemented contracts but **interactive completion after tools** still broken in live use.

---

## Suggested replan insertion point (for Claude to decide)

**Option A — Framework interrupt thesis:**
Insert new phases **38b–38f** (Interactive Completion Protocol) before resuming phase 39 tables.

**Option B — Parallel track:**
`ROADMAP_FRAMEWORK_INTERACTIVE.md` as sibling track; thesis 39+ blocked until interactive gate green.

**Option C — Merge into phase 41:**
E2E REPL smoke as thesis phase 41 prerequisite.

Document tradeoffs in replan output.

---

## Research questions (thesis) — unchanged

- RQ1/RQ2: memory, control, error-control ablation (phases 30–38 machinery exists)
- RQ3: interaction length / agent count
- Eval datasets: HumanEval, MBPP, SWE-bench Lite — **batch**, not REPL

Interactive REPL reliability may support thesis **engineering contribution** narrative but is not yet a phased roadmap item.

---

## Key repo paths

```
ROADMAP.md
ROADMAP_PHASES_NEXT.md
ROADMAP_PRODUCTION_AVIONA_V2.md
PROGRESS.md
docs/AVIONA_CURRENT_STATE.md
scripts/live_gate.py
scripts/debug_session.py
scripts/test-aviona.ps1
src/framework/orchestration/session.py
src/aviona/session.py
tests/aviona/JOURNEYS.md
```

---

## Git tags

- `pre-v2` — baseline 0.2.6 before Aviona v2
- v1 frozen at `4c638b3`
