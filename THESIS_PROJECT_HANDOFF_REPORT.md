# Thesis Project Handoff — SLM Agentic Framework

**For:** Claude (replan: **Aviona** = Claude Code–minimal in terminal; thesis benchmarks deferred)  
**UX contract:** `AVIONA_UX_SPEC.md`  
**Generated:** 2026-05-21 | **Git:** `f91cae4`  
**Roadmap in repo:** phases **0–41** defined in `ROADMAP.md`  
**Implementation status:** phases **0–38** `DONE` (structural); **39–41** `NOT_STARTED` (paused by user)  
**Pivot:** User is **not** spending API tokens on benchmark matrices now; replanning before resuming thesis phases 39+.

---

## 1. Executive summary

The codebase is a **working SLM agentic framework** (memory, control, error control, LangGraph production path) with a full **evaluation harness** for thesis ablations. It is **not yet** packaged as a daily-use production CLI.

**What works today (verified with dry-run + unit/integration tests)**

- **Session path:** `run_full_session(engine="graph")` — LangGraph + SqliteSaver; used by `eval/run_eval.py`.
- **Ablation A–D:** `eval/scenarios/ablation.py` — memory / control / error_control toggles.
- **Datasets:** HumanEval, discriminative slice, MBPP, multistep, SWE-bench adapters (SWE needs Docker for live).
- **Quality gate:** `assess_run()` rejects runs with too many `interaction_count=0` tasks.
- **Tests at handoff:** **181 unit** passed (9 skipped), **32 integration** passed.

**What the user wants next (not in ROADMAP 39–41)**

1. **Efficiency first** — lower token use (especially **output tokens**), faster runs, without sacrificing task success on real work.
2. **Production CLI** — installable on Windows (e.g. `aviona` on `PATH`), for **agentic workloads** (create/edit files, repo tasks), not only benchmarks.
3. **Dev-friendly install** — editable/local install that picks up code changes without reinstall friction.
4. **Thesis preserved** — framework and eval stay valid; **live benchmark matrices and thesis reports only after explicit approval**.

**What was intentionally deferred**

- Phase **31** live 12-run DeepSeek discriminative matrix (user stopped ablation; child Python PIDs had to be killed separately).
- Phases **32–37** live API runs (structural gates only in commit `101c993`).
- Phase **39–41** (LaTeX figures, docs bundle, e2e smoke) — **skipped for now**.

---

## 2. Repository map

| Area | Path | Role |
|------|------|------|
| Framework | `src/framework/` | SLM, memory, control, orchestration, tools, error_control |
| Evaluation | `eval/` | `run_eval`, adapters, metrics, scenarios, curated allowlist |
| Config | `configs/` | `models.yaml`, `eval.yaml`, `memory.yaml`, `cite_allowlist.yaml` |
| CLI scripts | `scripts/` | `generate_report.py`, `smoke_test.py`, `analyze_traces.py` |
| Tests | `tests/unit`, `tests/integration`, `tests/e2e` | Mocked / SQLite / real API (`@pytest.mark.e2e`) |
| Agent memory | `PROGRESS.md`, `ROADMAP.md` | Phase state and specs |
| Traces | `traces/` (gitignored) | JSONL aggregates, manifests, decisions |

**No production entry point yet** — there is no `aviona.exe` / `pyproject` console script for end-user workloads.

---

## 3. Cross-cutting architecture

| Pillar | Implementation |
|--------|----------------|
| Memory | `MemoryStores`, keyword or semantic retrieval, optional Redis |
| Control | `DecisionCycle`; transitions in Python only |
| Error control | Parser, truncation, quality gate, watchdog, sandbox |
| Orchestration | **Production:** `engine="graph"`; **Tests:** `engine="loop"` |
| SLM | `TrackingSLMClient`, profiles in `configs/models.yaml` |
| Eval | `run_eval` → `run_full_session`; ablation never raises on SLM error |

**Ablation configs:** A (none), B (memory), C (control+errors), D (full).

**Important fix (commit `101c993`):** `run_eval` now uses CLI `seed` instead of always forcing `eval.yaml` dataset `seed: 42` (required for multi-seed ablations).

---

## 4. Phase-by-phase (0–38)

| Range | Status | Notes |
|-------|--------|-------|
| 0–29 | DONE | Full framework + eval + LangGraph production + cost/curated/repro (see prior handoff detail) |
| 30 | DONE | Discriminative slice, `_difficulty.py`, `--dataset discriminative` |
| 31–37 | DONE (structural) | Cite sections, `retrieval_compare`, `efficiency`, dry-run gates; **no live cite traces** |
| 38 | DONE | `failure_taxonomy.py` + unit tests |
| 39–41 | NOT_STARTED | User paused for replan |

**Phase 31 caveat:** Partial live runs existed (`A_discriminative_*` with real API); user stopped processes. Allowlist section `humaneval_discriminative_deepseek` remains **empty** by design until approved benchmark sprint.

---

## 5. Evaluation results (thesis — deferred)

- **Canonical (still valid from earlier e2e):** `humaneval_hard` n=10 seed=42 — A/B 90% SR, C/D 100% SR (`configs/cite_allowlist.yaml`).
- **Discriminative matrix:** Not cited; incomplete / stopped.
- **Report:** `scripts/generate_report.py --curated` works when allowlist entries exist; `--efficiency` aggregates usage from cited runs (mostly zero on old traces).

Do **not** re-run live benchmarks until user approves API budget.

---

## 6. Production data flow (today vs target)

**Today (benchmark-oriented)**

```text
python -m eval.run_eval D discriminative --seed 42
  → load tasks from HuggingFace / curated ids
  → run_full_session per task
  → write traces/*.jsonl + manifest
```

**Target (Aviona = Claude Code–minimal)**

See **`AVIONA_UX_SPEC.md`**. Summary:

```text
cd D:\my-project
aviona
  → session in cwd
  → loop: gather context → act → verify (interrupt anytime)
  → tools: files, search, pytest/shell (guarded)
  → AVIONA.md project rules; session log under ~/.aviona/
  → checkpoints before edits; efficiency = low output tokens
```

**Not v1:** dataset benchmarks as main UI; `eval/` stays for thesis when approved.

---

## 7. Known issues

1. **No packaged CLI** — only module invocations (`python -m eval...`).
2. **Output token cost** — full prompts + tool dumps; truncation exists but not tuned for “daily driver” efficiency.
3. **Windows process cleanup** — stopping shell job may leave child `python.exe` ablation workers running (must kill by command line).
4. **LangGraph vs loop** — production eval uses graph; document clearly for any CLI wrapper.
5. **Thesis phases 39–41** — unimplemented; not blocking production replan.

---

## 8. Suggested roadmap after pause (headlines for Claude)

**Track A — Production “Aviona” (user priority)**

- A1 — Output-token budget: planner/executor caps, aggressive tool truncation, concise self-check, structured JSON-only where possible  
- A2 — Latency: parallel tool calls where safe, cache skill cards, reduce redundant Decision Cycle rounds  
- A3 — `pyproject.toml` → `aviona` on PATH; `pip install -e .` on Windows  
- A4 — **Interactive session REPL** in cwd (like `claude` in Claude Code): prompt loop, file ops, session context — map to `run_full_session` / graph  
- A5 — Path jail + write-guard for cwd; global secrets in `%USERPROFILE%\.aviona\`  
- A6 — Dev mode: editable install; `aviona doctor` for API probe without starting a session  
- A6 — Safety: write-guard, secret scan, dry-run / plan-only mode  

**Track B — Thesis completion (after user approval)**

- B1 — Resume ROADMAP 39–41 (LaTeX, repro zip, smoke e2e)  
- B2 — Live discriminative matrix + cite allowlist + curated report  
- B3 — slm_small + retrieval compare live runs  
- B4 — Final thesis tables/figures from cite-only pipeline  

---

## 9. Pointers

| Doc | Path |
|-----|------|
| Phase specs | `ROADMAP.md` |
| Agent state | `PROGRESS.md` |
| UX spec (Claude Code–minimal) | `AVIONA_UX_SPEC.md` |
| Replan prompt | `PROMPT_REPLAN_PRODUCTION.md` |
| Iterate skill | `.cursor/skills/thesis-iterate/SKILL.md` |
| Architecture rules | `.cursor/rules/thesis-roadmap.mdc` |
| Models / cost | `configs/models.yaml`, `eval/metrics/cost.py` |

---

## 10. Codebase file tree (high level)

```text
agentic-ai/
├── src/framework/          # Core agent framework
├── eval/                   # Benchmark harness (thesis)
├── configs/                # YAML configuration
├── scripts/                # Reports, smoke, analyze
├── tests/                  # unit / integration / e2e
├── PROGRESS.md ROADMAP.md
└── (no aviona CLI yet)
```
