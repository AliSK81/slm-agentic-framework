# Thesis Project Handoff — SLM Agentic Framework

**For:** Claude Opus (roadmap extension)  
**Generated:** 2026-05-21 | **Git:** `d0c28a5` | **Tag:** `v1.0-thesis-prototype`  
**Roadmap completed through phase:** 29  
**Next phase to plan:** 30

---

## 1. Executive summary

The SLM Agentic Framework thesis prototype is **feature-complete through ROADMAP phase 29**. All phases `0–29` are `DONE` in `PROGRESS.md`.

**What works end-to-end today**

- **Eval path:** `eval/run_eval.py` → `run_full_session()` (default **`engine=graph`**, LangGraph + SqliteSaver) with Decision Cycle, memory stores, tools, and ablation flags A–D.
- **Active provider:** DeepSeek `deepseek-v4-flash` (`configs/models.yaml` defaults); OpenRouter `slm_small` bundle (Qwen-7B + Devstral) is wired but needs live API budget.
- **Canonical cited results:** `humaneval_hard`, n=10, seed=42 — A/B **90% SR**, C/D **100% SR** (see `configs/cite_allowlist.yaml` and `thesis_evaluation_report.md` curated section).
- **Tests:** 160 unit (1 skipped Redis live), 32 integration — all pass at handoff time.

**What is not thesis-ready without more live runs**

- Multi-seed **statistical** ablation (seeds 41,42,43) — dry-run + harness exist; full live matrix mostly pending API budget.
- **MBPP** n=50, **SWE-bench** Docker instances, **agent-count** live CER, **keyword vs semantic** retrieval comparison — code exists; curated traces sparse or absent.
- **Cost/token columns** in old traces are zero (pre–phase-26 runs); re-run cited configs for non-zero usage metrics.

---

## 2. Repository map

| Area | Path | Role |
|------|------|------|
| Framework core | `src/framework/` | SLM client, memory, control, orchestration, tools, error control |
| Evaluation | `eval/` | `run_eval`, adapters, metrics, manifests, scenarios |
| Config | `configs/` | `models.yaml`, `eval.yaml`, `memory.yaml`, `cite_allowlist.yaml` |
| Tests | `tests/unit`, `tests/integration`, `tests/e2e` | Mocked unit; integration; real API e2e |
| Traces | `traces/` (gitignored) | Aggregate `*_*.jsonl`, manifests, decision JSONL |
| Reports | `scripts/generate_report.py`, `thesis_evaluation_report.md` | Curated + optional full history |
| Progress | `PROGRESS.md`, `ROADMAP.md` | Agent memory + phase specs |

---

## 3. Cross-cutting architecture (all phases)

| Pillar | Implementation | Notes |
|--------|----------------|-------|
| **Memory** | `MemoryStores` + SQLite default; optional `RedisBackend`; retrieval keyword (GA) or semantic (Chroma) | `MEMORY_RETRIEVAL_MODE` / `memory.yaml` `retrieval.mode` |
| **Control** | `DecisionCycle` — never raises on SLM failure; `next_state()` in Python only | Ablation toggles memory / control / error_control |
| **Error control** | Parser (8 patterns), quality gate, truncation, watchdog, sandbox | Phase 28: literal-newline repair, `ProfileResolutionError` |
| **Orchestration** | **Production:** `run_full_session(engine="graph")` — LangGraph nodes call same planner/executor | **Parity:** `engine="loop"` for tests; not used in eval |
| **SLM** | `client_for_role("planner"\|"executor")` — no model names at call sites | Usage tracked via `TrackingSLMClient` (phase 26) |
| **Eval validity** | `assess_run()` — invalid if >10% tasks have `interaction_count=0` | Ablation aborts on invalid non-dry runs |

**Ablation configs (eval.yaml)**

| Config | Memory | Control | Error control |
|--------|--------|---------|---------------|
| A | off | off | off |
| B | on | off | off |
| C | off | on | on |
| D | on | on | on |

---

## 4. Phase-by-phase (0–29)

Summaries from `PROGRESS.md` + code audit. Test gates passed unless noted.

### Phases 0–5 — Foundation

| Phase | Title | Built | Deviations |
|-------|-------|-------|------------|
| 0 | Bootstrap | Layout, requirements, pytest collect | — |
| 1 | SLM client | OpenRouter-compatible `SLMClient`, mocked tests | Production default is **DeepSeek**, not OpenRouter Qwen from early ROADMAP text |
| 2 | Memory stores | SQLite, 4 stores, retrieval index | Redis was stub until phase 29 |
| 3 | Working memory | Builder, skill cards, token ceiling | — |
| 4 | Error control | Parser, quality, truncation, thinking, watchdog, sandbox, checkpoint | ThinkingBudget untested until phase 28 |
| 5 | Tools | compile, pytest runner, file tools, search | — |

### Phases 6–12 — Agent loop + eval + e2e

| Phase | Title | Built | Deviations |
|-------|-------|-------|------------|
| 6 | Decision cycle | READ→PROPOSE→SELF_CHECK→ACT→RECORD | — |
| 7 | Workflow FSM | LangGraph + `next_state`, ledger | Was test-only until phase 25 |
| 8 | Agents | Planner/Executor, typed messages | — |
| 9 | E2E session | `run_full_session`, smoke | — |
| 10 | Eval harness | HumanEval/MBPP/SWE adapters, SR/CER | — |
| 11 | Ablation runner | A–D table, multi-config | — |
| 12 | Qualitative / e2e gate | 20-task D @ 100% canonical; invalid 70% run documented | `test_ablation_d_beats_a` skipped when A≈D |

### Phases 13–19 — Integrity + benchmarks + reflection

| Phase | Title | Built | Deviations |
|-------|-------|-------|------------|
| 13 | Run quality | Probe retry, zero-ix gate | — |
| 14 | Manifest + `--task-id` | `RunManifest`, per-run JSONL | — |
| 15 | Hard slice | `humaneval_hard`, curated id list | — |
| 16 | Interaction length | Synthetic L=2,4,6,8 multistep | — |
| 17 | Reflection on REVISE | SLM reflection capped per subtask | — |
| 18 | SLM small bundle | Qwen-7B + Devstral profiles | Live smoke needs key |
| 19 | Multi-seed ablation | `--seeds`, mean±std, quality abort | **Live** multi-seed humaneval_hard: user budget |

### Phases 20–24 — More benchmarks + analysis

| Phase | Title | Built | Deviations |
|-------|-------|-------|------------|
| 20 | MBPP | Adapter, dry-run gates | Live n=50 ablation not run |
| 21 | SWE-bench Docker | `swe_docker.py`, sandbox allow docker | Live instances not run |
| 22 | Agent-count | 1 vs 2 agents, CER column | Live API pending |
| 23 | Decision JSONL | Streamed decisions, `task_id` join | — |
| 24 | Qualitative metrics | Contradiction, oscillation, rationale coverage | Needs decision JSONL on cited runs |

### Phases 25–29 — Production polish

| Phase | Title | Built | Deviations |
|-------|-------|-------|------------|
| 25 | LangGraph production | SqliteSaver, `engine=graph` default, loop parity tests | ROADMAP once said loop default until parity — parity proven, graph is default |
| 26 | Cost accounting | `tokens_total`, `estimate_cost`, report columns | Old traces lack usage fields |
| 27 | Curated report | `cite_allowlist.yaml`, repro bundle, 95% CI helper | Phase-12 20-task runs not in allowlist until files exist |
| 28 | Hardening | `ProfileResolutionError`, newline JSON repair, ThinkingBudget tests | — |
| 29 | Retrieval + Redis | SemanticRetriever, RedisBackend, `--retrieval-mode` | Redis live test skipped without server |

---

## 5. Evaluation results

### Canonical (cite in thesis)

Source: `configs/cite_allowlist.yaml`, validated by `scripts/generate_report.py --curated --dry-run`.

| Config | Dataset | n | Seed | SR | CER | Run ID |
|--------|---------|---|------|-----|-----|--------|
| A | humaneval_hard | 10 | 42 | 90% | 20.8% | `A_humaneval_hard_20260520T125039Z` |
| B | humaneval_hard | 10 | 42 | 90% | 20.0% | `B_humaneval_hard_20260520T125743Z` |
| C | humaneval_hard | 10 | 42 | 100% | 0% | `C_humaneval_hard_20260520T130606Z` |
| D | humaneval_hard | 10 | 42 | 100% | 0% | `D_humaneval_hard_20260520T131220Z` |

**Do not cite:** `D_humaneval_20260520T085222Z` (70% SR, six zero-interaction tasks — network failure).

**Phase-12 reference runs** (20-task humaneval, seed=42): `D_humaneval_20260520T082826Z` (100%), `A_humaneval_20260520T083955Z` (100%) — add to allowlist when trace files are present.

### Historical / experimental

`thesis_evaluation_report.md` (`--curated --all`) lists 150+ aggregate JSONL files including dry-runs, failed probes, and early experiments. **Do not use the aggregate table for thesis claims** — use curated section only.

Log reference: `logs/e2e_20260520T125009Z.log` (A/B 90%, C/D 100% on humaneval_hard).

---

## 6. Production data flow

```text
run_eval / ablation
  → run_single_task()
    → run_full_session(engine="graph")   # LangGraph + SqliteSaver
      → validate_slm_api_key()           # probe with retry
      → PlannerAgent / ExecutorAgent
        → DecisionCycle → SLMClient (TrackingSLMClient)
      → SessionOutcome → RunResult JSONL row
  → write_manifest + optional decisions JSONL
  → assess_run() quality sidecar
```

**Checkpointing:** JSON session checkpoints under `traces/checkpoints/`; LangGraph SQLite under `{checkpoint_dir}/{session_id}_langgraph.sqlite`.

---

## 7. Known issues and limitations

1. **Thin live evidence for RQ1/RQ3** — Many scenarios are dry-run complete but not backed by multi-seed curated traces.
2. **Token/cost data** — Pre-phase-26 JSONL rows show zeros; re-run cited configs for thesis efficiency chapter.
3. **D vs A delta** — On cited humaneval_hard slice, D≈C at 100% vs A at 90%; `test_ablation_d_beats_a` may skip; thesis should discuss ceiling effect on n=10.
4. **Redis** — Implemented; live round-trip test skipped without local Redis.
5. **Semantic retrieval** — Implemented; no curated A/B comparison run (keyword vs semantic) in `cite_allowlist.yaml`.
6. **traces/** gitignored — Repro bundle: `python scripts/make_repro_bundle.py` for cited artifacts only.

---

## 8. Suggested phases after 29 (headlines only)

For Claude to expand into full `ROADMAP.md` sections starting at **phase 30**:

1. **Live multi-seed humaneval_hard ablation** — seeds 41,42,43; update `cite_allowlist.yaml`; SR/CER mean±95% CI in results chapter.
2. **Keyword vs semantic retrieval live comparison** — B/D arms with `--retrieval-mode`; attribute SR/CER delta to mechanism (RQ1).
3. **Re-run cited configs with cost accounting** — refresh allowlisted JSONL with `tokens_total` / `estimated_usd`.
4. **MBPP full ablation n=50** — A–D traces + manifest + quality gate.
5. **SWE-bench Lite pilot** — 5–10 instances, Docker grading path validation.
6. **Agent-count live experiment** — multistep, CER-focused table for RQ3.
7. **OpenRouter slm_small live matrix** — true-SLM cost/latency comparison vs DeepSeek.
8. **Phase-12 runs into allowlist** — merge 20-task canonical humaneval traces when on disk.
9. **Qualitative metrics on cited runs** — `--qualitative` / `--compare-a-d` for chapter RQ2.
10. **Decision-log interpretability appendix** — `analyze_traces --session` samples per config.
11. **Interaction-length live sweep** — L=2,4,6,8 with manifests (RQ3).
12. **Failure taxonomy from traces** — classify escalate vs max_steps vs unresolvable across configs.
13. **Thesis figure automation** — SR/CER bar charts from curated report only.
14. **LaTeX table export** — `generate_report --latex` or pandoc pipeline.
15. **E2E regression CI** — nightly humaneval_hard n=3 smoke (optional GitHub Action).
16. **Redis-backed session store pilot** — `MEMORY_BACKEND=redis` under load.
17. **Handoff reproducibility package** — zip `artifacts/repro_bundle` + MANIFEST_INDEX for committee.
18. **Documentation pass** — architecture diagram aligned with graph-default reality.
19. **Performance profiling** — latency breakdown planner vs executor per session.
20. **Roadmap phase 40+ buffer** — committee-requested extensions (human subjects, user study, etc.).

---

## 9. Pointers

| Resource | Path |
|----------|------|
| Phase log | `PROGRESS.md` |
| Specs | `ROADMAP.md` |
| Extend prompt | `PROMPT_EXTEND_ROADMAP.md` |
| Curated runs | `configs/cite_allowlist.yaml` |
| Latest report | `thesis_evaluation_report.md` |
| Iterate skill | `.cursor/skills/thesis-iterate/SKILL.md` |
| Thesis standards | `.cursor/rules/thesis-roadmap.mdc` |

---

## 10. Codebase file tree (high level)

```text
agentic-ai/
├── configs/          models, eval, memory, cite_allowlist, humaneval_hard_ids
├── src/framework/
│   ├── slm/          client, config, registry, usage, skills
│   ├── memory/       stores, retrieval, working_memory, reflection, backend
│   ├── control/      cycle, workflow, self_check, ablation, ledger
│   ├── orchestration/ session, graph, planner, executor, messages
│   ├── tools/        test_runner, file_tools, compile, search
│   └── error_control/ parser, quality, truncation, thinking, watchdog, sandbox
├── eval/             run_eval, manifest, metrics, curated, scenarios, datasets
├── scripts/          generate_report, make_repro_bundle, analyze_traces, smoke_test
├── tests/            unit, integration, e2e
├── traces/           (gitignored) JSONL, manifests, checkpoints
├── logs/             e2e logs
├── PROGRESS.md
└── ROADMAP.md
```

---

*End of handoff — merge `ROADMAP_PHASES_NEXT.md` from Claude starting at phase 30, then resume with `thesis-iterate`.*
