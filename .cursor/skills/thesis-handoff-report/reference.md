# Handoff Report Reference

## Phase resolution (every run)

```text
last_roadmap_phase = max N from ROADMAP.md Phase Overview or ## PHASE N headings
current_phase      = PROGRESS.md current_phase
next_phase         = last_roadmap_phase + 1
```

Handoff is valid only when phases `0..last_roadmap_phase` are all `DONE` in `PROGRESS.md`.

## Glossary

| Term | Meaning |
|------|---------|
| **Live path** | `run_full_session()` in `session.py` — used by `run_eval` and e2e |
| **LangGraph path** | `build_graph()` — integration tests only |
| **Canonical run** | Trace JSONL cited in thesis (provider, n, seed, config) |
| **Zero-ix run** | `interaction_count=0` — invalid for ablation claims |
| **Config A–D** | `configs/eval.yaml` → `AblationSettings` |

## `THESIS_PROJECT_HANDOFF_REPORT.md` skeleton

```markdown
# Thesis Project Handoff — SLM Agentic Framework

**For:** Claude Opus (roadmap extension)
**Generated:** <date> | **Git:** `<hash>`
**Roadmap completed through phase:** {last_roadmap_phase}
**Next phase to plan:** {next_phase}

## 1. Executive summary
## 2. Repository map
## 3. Cross-cutting (all phases)
## 4. Phase-by-phase (0–{last_roadmap_phase})
### Phase K — <title from ROADMAP>
## 5. Evaluation results
## 6. Production data flow
## 7. Known issues
## 8. Suggested phases after {last_roadmap_phase} (headlines only)
## 9. Pointers
## 10. Codebase file tree
```

## Per-phase audit

For each `## PHASE N` block in `ROADMAP.md`, read the files named in that section's Tasks/specs. Do not rely on a fixed global path table — the roadmap grows over time.

## `PROMPT_EXTEND_ROADMAP.md` (regenerate with resolved numbers)

Must state explicitly:

- Completed phases: `0` through `{last_roadmap_phase}`
- New content starts at `## PHASE {next_phase}`
- Claude output: **`ROADMAP_PHASES_NEXT.md`** only
- Do not rewrite existing phase sections in `ROADMAP.md`

## Anti-patterns

- Hardcoding phase numbers inside `.cursor/skills/` (always resolve from files)
- 4000-line reports with full tree + all per-task rows
- Scratch artifacts: `_all_runs.json`, `build_full_handoff.py`
- Claiming LangGraph runs production eval sessions
