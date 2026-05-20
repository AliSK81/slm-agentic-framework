---

## Phase Overview — Phases 30+

> **Context for the implementing agent:** Phases 0–29 are DONE. The framework, eval harness, ablation runner,
> manifests, quality gate, decision JSONL, qualitative metrics, cost accounting, curated allowlist, and the
> LangGraph production path (`engine="graph"` + SqliteSaver) all exist and are dry-run-tested. **What is
> missing is curated, live, multi-seed evidence and the thesis write-up artifacts.** Phases 13–29 *built*
> the machinery; phases 30+ *run* it to produce citable numbers, then turn those numbers into tables and
> figures. Two facts from the handoff drive the ordering: (1) the cited `humaneval_hard` n=10 slice is
> near-ceiling — A/B 90% SR, C/D 100% SR — so the A→D contribution can't be cleanly separated (§7.3); and
> (2) the production default is DeepSeek `deepseek-v4-flash`, whose "small" status is contestable for a
> thesis about SLMs (§1, §4). Phase 30 fixes (1); Phase 32 addresses (2).

```
PHASE 30 → Discriminative hard slice (break the n=10 ceiling effect)        [RQ2]
PHASE 31 → Live multi-seed A–D ablation, DeepSeek (mean ± 95% CI)           [RQ2] [REQUIRES_USER_INPUT]
PHASE 32 → True-SLM live matrix (Qwen-7B + Devstral via OpenRouter)         [RQ2] [REQUIRES_USER_INPUT]
PHASE 33 → Keyword vs semantic retrieval live comparison                    [RQ1] [REQUIRES_USER_INPUT]
PHASE 34 → Efficiency chapter: SLM-vs-LLM cost/latency/token table          [REQUIRES_USER_INPUT]
PHASE 35 → MBPP full ablation n=50                                          [REQUIRES_USER_INPUT]
PHASE 36 → RQ3 live evidence: interaction-length + agent-count CER sweeps    [RQ3] [REQUIRES_USER_INPUT]
PHASE 37 → SWE-bench Lite pilot (5–10 instances)                            [REQUIRES_USER_INPUT]
PHASE 38 → Qualitative metrics + failure taxonomy on cited runs             [RQ1/RQ2]
PHASE 39 → Thesis tables & figures automation (curated-only, LaTeX)
PHASE 40 → Documentation pass + zipped reproducibility package
PHASE 41 → E2E regression smoke + optional Redis pilot                      [REQUIRES_USER_INPUT optional]
```

Same contract as the rest of `ROADMAP.md`: **Goal → Tasks → Acceptance tests → Commit**. Architecture
constraints are non-negotiable and untouched here: agents pass state only through memory stores; agents
communicate only via typed Pydantic messages; the SLM never decides transitions (`next_state()` is pure
Python); every LLM call goes through the Decision Cycle; tools keep the write-guard and atomic checkpoints.

> **Evidence phases never fabricate numbers.** For every `[REQUIRES_USER_INPUT]` run phase, the CI-checkable
> gate is a `--dry-run` / structural test that passes immediately (proving wiring) **plus** an evidence-gate
> test that passes only once the live run is on disk, has passed `assess_run()`, and is entered in
> `configs/cite_allowlist.yaml`. The evidence-gate test **skips cleanly** when traces are absent (CI without
> budget) and is the true DONE criterion once the live run completes. Any "D beats A" assertion uses the
> existing **skip-not-fail** pattern so a null/ceiling result is recorded, never faked.

---

## PHASE 30 — Discriminative Hard Slice (Break the Ceiling Effect) [RQ2]

**Goal:** The cited `humaneval_hard` n=10 slice is near-ceiling (A/B 90%, C/D 100%), so the memory/control/
error-control contribution can't be statistically separated (handoff §7.3). Build a larger, deterministically
harder, *frozen* slice on which config A drops well below ceiling, making the A→D delta measurable. No live API.

### Tasks

- `eval/datasets/_difficulty.py` (new) — extract the `difficulty_of(...)` heuristic shared by the HumanEval and
  MBPP adapters into one module (currently duplicated since Phase 15/20); keep behaviour identical (regression).
- `configs/humaneval_hard_ids.txt` — expand the frozen curated id list to ≥30 ids, selected as the top
  difficulty quantile (by `prompt_loc`, `n_assertions`, nested-loop/DP keywords). Exclude ids that config A
  already solves at every seed in existing traces (those add ceiling, not signal).
- `configs/eval.yaml` — add a frozen alias `discriminative: {dataset: humaneval, ids_file: humaneval_hard_ids.txt, n: 30, seed: 42}`. Leave `humaneval_hard` unchanged for backward compatibility.
- `eval/run_eval.py` / `eval/scenarios/ablation.py` — accept `--dataset discriminative`.

### Acceptance tests — extend `tests/unit/test_difficulty_slices.py`

```python
def test_difficulty_module_shared_by_humaneval_and_mbpp():   # both import eval.datasets._difficulty
def test_hard_slice_size_at_least_30():
def test_slice_is_frozen_and_deterministic():                # same ids for fixed seed across two loads
def test_discriminative_alias_resolves_in_eval_yaml():
def test_existing_humaneval_hard_alias_unchanged():          # regression
```

CLI gate (no budget):
```
python -m eval.run_eval --config A --dataset discriminative --n 5 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-30: discriminative frozen hard slice to break ceiling effect (RQ2)"
```

---

## PHASE 31 — Live Multi-Seed A–D Ablation, DeepSeek (mean ± 95% CI) [RQ2] [REQUIRES_USER_INPUT]

**Goal:** Produce the statistical core of the RQ2 result: A/B/C/D on the discriminative slice across seeds
41/42/43 with DeepSeek, reported as SR/CER mean ± 95% CI, with valid runs entered in the cite allowlist and
the curated report regenerated.

> `[REQUIRES_USER_INPUT]` — DeepSeek API budget. Cost ≈ 4 configs × 30 tasks × 3 seeds sessions. Confirm budget
> before running.

### Tasks

- Live run: `python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --profile-bundle deepseek`
  (quality-aborts on any invalid run — wired in Phase 19).
- `configs/cite_allowlist.yaml` — add section `humaneval_discriminative_deepseek` listing the 12 valid run ids
  (4 configs × 3 seeds), each with seed and quality-gate status.
- `tests/unit/test_cite_allowlist.py` (new) — validate every allowlist entry references an existing JSONL that
  passed `assess_run()` and carries required fields; **skip** entries whose trace file is absent (CI-safe).
- Regenerate: `python scripts/generate_report.py --curated` → curated section now shows per-config mean ± 95% CI.

### Acceptance tests

Structural gate (no budget):
```
python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --dry-run
pytest tests/unit/test_cite_allowlist.py        # passes/skips cleanly with no traces present
```

Evidence gate (after live run):
```python
def test_deepseek_discriminative_section_complete_and_valid():   # no skips for the 12 new ids
@pytest.mark.e2e
def test_ablation_d_geq_a_discriminative():
    """If D.SR >= A.SR + 5pp AND D.CER < A.CER → pass; else pytest.skip recording observed means
       (document ceiling, never assert a fabricated win)."""
```

### Commit
```
git add -A && git commit -m "phase-31: live multi-seed A-D ablation (DeepSeek) + allowlist + 95% CI (RQ2)"
```

---

## PHASE 32 — True-SLM Live Matrix (Qwen-7B + Devstral) [RQ2] [REQUIRES_USER_INPUT]

**Goal:** Protect the headline claim — "acceptable performance **without relying on LLMs**." The production
default is DeepSeek `v4-flash`, whose <30B "small" status is contestable (handoff §1, §4 Phase 1). Run the
A–D matrix on the `slm_small` bundle (Qwen-7B planner + Devstral executor via OpenRouter) so the thesis result
rests on a genuine SLM. A weaker model is expected to show *larger* A→D separation — strong RQ2 evidence.

> `[REQUIRES_USER_INPUT]` — `OPENROUTER_API_KEY` with budget, and committee confirmation that Qwen-7B/Devstral
> qualify as "small". The agent must not create accounts or write keys to the repo; the user fills `.env`.

### Tasks

- Verify bundle: `python scripts/smoke_test.py --bundle slm_small` must print `OUTCOME: solved`.
- Live run: `python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --profile-bundle slm_small`.
- `configs/cite_allowlist.yaml` — add section `humaneval_discriminative_slm_small`; quality-validate all runs.
- Regenerate curated report (now two provider blocks: DeepSeek vs slm_small).
- Record (analysis note in `thesis_evaluation_report.md`, not asserted) whether the D→A gap is larger on
  slm_small than on DeepSeek — the expected mechanism-helps-weaker-model finding.

### Acceptance tests

Structural gate:
```
pytest tests/unit/test_slm_profiles.py
python -m eval.scenarios.ablation --dataset discriminative --profile-bundle slm_small --dry-run
```

Evidence gate (after live run): `test_slm_small_discriminative_section_complete_and_valid()` in
`tests/unit/test_cite_allowlist.py` passes with no skips.

### Commit
```
git add -A && git commit -m "phase-32: true-SLM (Qwen-7B+Devstral) live A-D matrix (RQ2)"
```

---

## PHASE 33 — Keyword vs Semantic Retrieval Live Comparison [RQ1] [REQUIRES_USER_INPUT]

**Goal:** Direct RQ1 evidence — does the *memory mechanism* matter? Compare keyword (Generative Agents) vs
semantic (Chroma) retrieval on the memory-bearing configs (B and D), attributing any SR/CER and coherence delta
to the retrieval mechanism. Both modes exist (Phase 29) but no curated comparison run does (§7.5).

> `[REQUIRES_USER_INPUT]` — API budget. Reuse whichever provider bundle the committee designates as canonical.

### Tasks

- `eval/scenarios/retrieval_compare.py` (new) — thin wrapper over the ablation runner restricted to configs
  **B and D** (the only configs with memory on), iterating `--retrieval-mode keyword|semantic` over seeds.
- Live run on the discriminative slice, seeds 41/42/43, both modes.
- `configs/cite_allowlist.yaml` — sections `retrieval_keyword` and `retrieval_semantic`.
- Cross-link to Phase 24 metrics: compute contradiction & oscillation per mode (does semantic retrieval reduce
  incoherence as interaction length grows?).

### Acceptance tests — `tests/unit/test_retrieval_compare.py`

```python
def test_retrieval_compare_runs_only_b_and_d():
def test_retrieval_mode_flag_propagates_to_sessions():
def test_compare_table_has_mode_and_config_columns():
```

CLI gate (no budget):
```
python -m eval.scenarios.retrieval_compare --dataset discriminative --dry-run
```

Evidence gate: `test_retrieval_sections_complete_and_valid()` in `tests/unit/test_cite_allowlist.py`.

### Commit
```
git add -A && git commit -m "phase-33: keyword vs semantic retrieval live comparison (RQ1)"
```

---

## PHASE 34 — Efficiency Chapter: SLM-vs-LLM Cost/Latency/Token Table [REQUIRES_USER_INPUT]

**Goal:** Substantiate the thesis's "low-cost / locally deployable" claim with measured per-task tokens,
latency, and estimated cost, comparing slm_small against DeepSeek on the same slice. Pre–Phase-26 traces show
zero usage (§7.2); the Phase-31/32 runs carry real usage via `TrackingSLMClient`, so this phase aggregates them.

> `[REQUIRES_USER_INPUT]` — depends on Phases 31 and 32 having produced cited runs with non-zero usage fields.

### Tasks

- `configs/models.yaml` — add `price_per_1k_in` / `price_per_1k_out` for `deepseek-v4-flash`, `qwen2.5-coder-7b`,
  and `devstral-small` (use 0 with an explicit `price_known: false` flag where a public price is unavailable).
- `eval/metrics/efficiency.py` (new) — aggregate `tokens_total`, `latency_ms_total`, `llm_calls`, and
  `estimate_cost(...)` (Phase 26) per provider × config from cited JSONL; emit per-task means.
- `scripts/generate_report.py` — add `--efficiency` producing a provider × config table: SR, CER, tokens/task,
  latency/task, $/task, with unknown prices clearly flagged (never silently 0).

### Acceptance tests — `tests/unit/test_efficiency.py`

```python
def test_efficiency_aggregates_usage_per_provider_config():
def test_estimated_usd_uses_price_table():
def test_unknown_price_is_flagged_not_silently_zero():
def test_efficiency_table_compares_deepseek_vs_slm_small():
```

CLI gate:
```
python scripts/generate_report.py --efficiency --dry-run
```

### Commit
```
git add -A && git commit -m "phase-34: efficiency chapter (SLM-vs-LLM cost/latency/token table)"
```

---

## PHASE 35 — MBPP Full Ablation n=50 [REQUIRES_USER_INPUT]

**Goal:** A second benchmark for external validity — A–D on MBPP n=50 (handoff §7: adapter ready, no live runs),
so the thesis isn't a single-dataset result.

> `[REQUIRES_USER_INPUT]` — API budget.

### Tasks

- Confirm the MBPP adapter maps to the session task shape and `difficulty_of` works on `MBPPTask`
  (Phase 20/30 shared module).
- Live run: `python -m eval.scenarios.ablation --dataset mbpp --n 50 --seeds 41,42,43` (or seed 42 if budget-limited).
- Quality-validate; `configs/cite_allowlist.yaml` section `mbpp_50`; regenerate curated report.

### Acceptance tests

CLI gate (no budget):
```
python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run
```

Evidence gate: `test_mbpp50_section_complete_and_valid()` in `tests/unit/test_cite_allowlist.py`; honest
`@pytest.mark.e2e test_ablation_d_geq_a_mbpp()` (skip-not-fail).

### Commit
```
git add -A && git commit -m "phase-35: MBPP n=50 A-D ablation + curated traces"
```

---

## PHASE 36 — RQ3 Live Evidence: Interaction-Length + Agent-Count CER Sweeps [RQ3] [REQUIRES_USER_INPUT]

**Goal:** The central RQ3 numbers: cumulative error (CER) as a function of interaction length (L=2,4,6,8) and of
agent count (1 vs 2 agents). Both harnesses exist (Phases 16, 22) but lack live curated traces, and the
Phase-22 contradiction column is still stubbed pending decision JSONL (now available from Phase 23).

> `[REQUIRES_USER_INPUT]` — API budget.

### Tasks

- Live interaction-length sweep: `python -m eval.scenarios.interaction_length --config A --config D --levels 2,4,6,8 --seeds 41,42,43` (A and D so the framework delta is visible as L grows).
- Live agent-count: `python -m eval.scenarios.agent_count --dataset multistep --seeds 41,42,43`.
- `eval/scenarios/agent_count.py` — replace the contradiction-count stub with the real value computed from the
  Phase-23 decision JSONL (`eval/decision_log.py`).
- Quality-validate; `configs/cite_allowlist.yaml` sections `rq3_interaction_length`, `rq3_agent_count`.
- Produce CER-vs-L and CER-vs-agents tables (expectation, not asserted: A's CER rises faster with L than D's).

### Acceptance tests

```python
# tests/unit/test_ablation_runner.py (extend)
def test_agent_count_contradiction_from_decision_log():    # no longer a stub
# tests/unit/test_interaction_length.py (extend)
def test_sweep_emits_cer_per_level_per_config():
```

CLI gates (no budget):
```
python -m eval.scenarios.interaction_length --config D --levels 2,4,6,8 --dry-run
python -m eval.scenarios.agent_count --dataset multistep --dry-run
```

Evidence gate: `test_rq3_sections_complete_and_valid()` in `tests/unit/test_cite_allowlist.py`.

### Commit
```
git add -A && git commit -m "phase-36: RQ3 live evidence (interaction-length + agent-count CER sweeps)"
```

---

## PHASE 37 — SWE-bench Lite Pilot (5–10 instances) [REQUIRES_USER_INPUT]

**Goal:** Validate the Docker grading path (Phase 21) on a small set of real SWE-bench Lite instances and report
whether the framework completes genuine repository-repair sessions. Pilot scale — reported as illustrative, not
a full benchmark claim.

> `[REQUIRES_USER_INPUT]` — Docker available on the host **and** API budget. The agent must not install Docker or
> pull untrusted images without the user enabling it.

### Tasks

- Run config D on 5–10 SWE-bench Lite instances via the Phase-21 Docker harness; capture `FAIL_TO_PASS` outcomes.
- Quality-validate (no zero-interaction); `configs/cite_allowlist.yaml` section `swebench_pilot` clearly marked
  pilot/illustrative (small n).
- Record per-instance outcome + a short failure note for any unresolved instance (feeds Phase 38 taxonomy).

### Acceptance tests — `tests/unit/test_swebench_docker.py` (extend)

```python
def test_pilot_run_records_per_instance_outcome():
def test_swe_pilot_skips_cleanly_when_docker_absent(monkeypatch):
```

CLI gate (structural; Docker run is the evidence step):
```
python -m eval.run_eval --config D --dataset swebench --n 1 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-37: SWE-bench Lite pilot (Docker grading path validation)"
```

---

## PHASE 38 — Qualitative Metrics + Failure Taxonomy on Cited Runs [RQ1/RQ2]

**Goal:** Turn the cited decision-log JSONL (from Phases 31–33, 36) into the thesis's qualitative chapter:
contradiction rate, oscillation index, and rationale coverage per config (Phase 24), plus a failure taxonomy
(escalate vs max_steps vs unresolvable) across configs. Deterministic, no budget.

### Tasks

- `eval/metrics/failure_taxonomy.py` (new) — classify each `RunResult.outcome` plus its escalation reason from
  the decision JSONL into a typed taxonomy; produce counts per config and per provider.
- `scripts/analyze_traces.py` — add `--taxonomy`; ensure `--qualitative` and `--compare-a-d` run over the cited
  run glob and emit the A-vs-D and keyword-vs-semantic comparison tables for the chapter.
- Output a single qualitative summary table (coherence/interpretability/stability + taxonomy) per provider.

### Acceptance tests — `tests/unit/test_failure_taxonomy.py` (+ extend `test_qualitative_metrics.py`)

```python
def test_taxonomy_classifies_each_outcome_kind():
def test_taxonomy_counts_per_config_and_provider():
def test_taxonomy_reads_decision_jsonl_not_checkpoints():
def test_qualitative_runs_over_cited_glob():
```

CLI gate:
```
python scripts/analyze_traces.py --qualitative --compare-a-d --taxonomy --dry-run
```

### Commit
```
git add -A && git commit -m "phase-38: qualitative metrics + failure taxonomy on cited runs (RQ1/RQ2)"
```

---

## PHASE 39 — Thesis Tables & Figures Automation (Curated-Only, LaTeX)

**Goal:** Auto-generate the results-chapter tables and figures from **curated runs only** — never the dirty
aggregate — in LaTeX + PNG, so the write-up is reproducible and cannot accidentally include a do-not-cite run
(e.g. `D_humaneval_20260520T085222Z`).

### Tasks

- `scripts/make_figures.py` (new, matplotlib) — SR and CER bar charts per config, CER-vs-L line plot, and the
  DeepSeek-vs-slm_small comparison; reads the curated report only; writes `artifacts/figures/*.png`.
- `scripts/generate_report.py` — add `--latex` emitting LaTeX tables (SR/CER mean ± 95% CI, efficiency,
  qualitative) to `artifacts/tables/*.tex`.
- Guard: both tools **refuse** to emit if any referenced run is missing from `cite_allowlist.yaml` or failed
  `assess_run()`.

### Acceptance tests — `tests/unit/test_report_latex.py`, `tests/unit/test_figures.py`

```python
def test_latex_tables_emitted_with_ci():
def test_latex_refuses_noncurated_run():
def test_figures_generated_from_curated_only():
def test_figure_refuses_run_that_failed_quality_gate():
```

CLI gate:
```
python scripts/generate_report.py --latex --dry-run && python scripts/make_figures.py --dry-run
```

### Commit
```
git add -A && git commit -m "phase-39: thesis tables + figures automation (curated-only, LaTeX export)"
```

---

## PHASE 40 — Documentation Pass + Zipped Reproducibility Package

**Goal:** Align the docs with the graph-default reality (the early ROADMAP text still implies a loop default /
OpenRouter-only client) and ship a committee-ready, secret-free reproducibility package.

### Tasks

- `docs/architecture.md` (new) — a diagram + prose reflecting the actual production path
  (`run_full_session(engine="graph")` + SqliteSaver), the three pillars, and the A–D ablation matrix; remove
  stale loop-default / OpenRouter-only claims.
- `docs/reproducibility.md` (new) — exact commands to reproduce each cited table and figure from manifests.
- `scripts/make_repro_bundle.py` — add `--zip`: bundle cited JSONL + manifests + decision JSONL + `artifacts/tables`
  + `artifacts/figures` + `MANIFEST_INDEX.md` into `artifacts/repro_bundle.zip`; **no** keys, **no** full workspaces.

### Acceptance tests — `tests/unit/test_repro_package.py`

```python
def test_bundle_zip_created():
def test_bundle_contains_no_secrets():            # scans for key/token-shaped strings
def test_bundle_includes_manifest_index():
def test_bundle_only_references_cited_runs():
def test_architecture_doc_states_graph_default():
```

CLI gate:
```
python scripts/make_repro_bundle.py --zip --dry-run
```

### Commit
```
git add -A && git commit -m "phase-40: documentation pass + zipped reproducibility package"
```

---

## PHASE 41 — E2E Regression Smoke + Optional Redis Pilot [REQUIRES_USER_INPUT optional]

**Goal:** Guard against regressions during the write-up sprint, and (optionally) validate the Redis backend
against a real server (the Phase-29 live round-trip is currently skipped, §7.4).

> `[REQUIRES_USER_INPUT]` (optional) — the smoke run needs a provider key; the Redis pilot needs a local Redis
> server. Both degrade to **skip** when unavailable so CI stays green.

### Tasks

- `tests/e2e/test_regression_smoke.py` (new) — config D on `humaneval_hard` n=3, marked `@pytest.mark.e2e`;
  asserts the session reaches `solved`/`escalate` without crashing and the run passes `assess_run()`.
- `.github/workflows/smoke.yml` (optional) — on dispatch/nightly, run the smoke when a provider key secret is
  present; skip if absent.
- Redis pilot — with `MEMORY_BACKEND=redis` and a local server, run the existing skipped
  `test_redis_backend` live round-trip; note behaviour under repeated sessions in `docs/reproducibility.md`.

### Acceptance tests

```
pytest tests/e2e/test_regression_smoke.py --collect-only      # structural, no key needed
pytest tests/unit/test_redis_backend.py                       # skips without server, passes with
```

Evidence step (needs key): `pytest tests/e2e/test_regression_smoke.py -m e2e`.

### Commit
```
git add -A && git commit -m "phase-41: e2e regression smoke + optional Redis live pilot"
```

---

## Test Gates — Phases 30+

```bash
# Before marking any phase DONE, run its gate:
PHASE 30: pytest tests/unit/test_difficulty_slices.py && python -m eval.run_eval --config A --dataset discriminative --n 5 --dry-run
PHASE 31: python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --dry-run && pytest tests/unit/test_cite_allowlist.py
PHASE 32: pytest tests/unit/test_slm_profiles.py && python -m eval.scenarios.ablation --dataset discriminative --profile-bundle slm_small --dry-run
PHASE 33: pytest tests/unit/test_retrieval_compare.py && python -m eval.scenarios.retrieval_compare --dataset discriminative --dry-run
PHASE 34: pytest tests/unit/test_efficiency.py && python scripts/generate_report.py --efficiency --dry-run
PHASE 35: python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run
PHASE 36: pytest tests/unit/test_ablation_runner.py tests/unit/test_interaction_length.py && python -m eval.scenarios.agent_count --dataset multistep --dry-run
PHASE 37: pytest tests/unit/test_swebench_docker.py            # + Docker instance run (needs Docker + key)
PHASE 38: pytest tests/unit/test_failure_taxonomy.py tests/unit/test_qualitative_metrics.py
PHASE 39: pytest tests/unit/test_report_latex.py tests/unit/test_figures.py && python scripts/generate_report.py --latex --dry-run
PHASE 40: pytest tests/unit/test_repro_package.py && python scripts/make_repro_bundle.py --zip --dry-run
PHASE 41: pytest tests/e2e/test_regression_smoke.py --collect-only && pytest tests/unit/test_redis_backend.py
```

> **Dependency order:** 30 unblocks all live ablation (31, 32, 33, 35, 36 run on the discriminative slice).
> 34 depends on 31+32 (needs cited runs with non-zero usage). 38/39 depend on the cited decision JSONL and
> curated runs that 31–33 and 36 produce. 40 and 41 are independent and can run anytime. If budget is tight,
> the minimum publishable core is **30 → 31 → 32 → 38 → 39** (discriminative slice, both providers, qualitative
> analysis, automated tables) — 33/35/36/37 add breadth, 34/40/41 add polish.
