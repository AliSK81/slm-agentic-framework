---

## Phase Overview — Phases 13+

> **Context for the implementing agent:** Phases 0–12 are DONE. The production path is the imperative
> `run_full_session()` loop in `orchestration/session.py` (LangGraph is off this path), and the active
> provider is **DeepSeek `deepseek-v4-flash`**, not the OpenRouter Qwen/Devstral spec in Phases 0–8.
> The headline thesis result is currently **not demonstrable**: on the canonical HumanEval-20 slice
> `A = D = 100% SR`, and the B/C runs are invalid (`interaction_count = 0`, infrastructure failure, not a
> framework comparison). Phases 13–29 exist to (a) make the A/B/C/D ablation *valid and measurable*,
> (b) produce the MBPP/SWE/agent-count evidence the thesis promises, and (c) close the production gaps
> the thesis claims but does not run. Each phase ties to **RQ1 (memory)**, **RQ2 (decision accuracy)**,
> or **RQ3 (cumulative error vs. agent/interaction count)** only where the codebase supports it.

```
PHASE 13 → Run integrity: API probe retry + run-level quality gate
PHASE 14 → Eval CLI: single-task rerun + per-run reproducibility manifest
PHASE 15 → Measurable difficulty slices (HumanEval hard-only + stratified)
PHASE 16 → Controlled multi-step scenarios (interaction-length sweep)        [RQ3]
PHASE 17 → Reflection wired into REVISE                                      [RQ2/RQ3]
PHASE 18 → True-SLM profile + provider replication                          [REQUIRES_USER_INPUT]
PHASE 19 → Valid full ablation A–D (multi-seed, manifested)                  [REQUIRES_USER_INPUT]
PHASE 20 → MBPP ablation + traces                                           [REQUIRES_USER_INPUT]
PHASE 21 → SWE-bench Lite Docker runner                                      [REQUIRES_USER_INPUT]
PHASE 22 → Agent-count experiment (1 vs 2 agents, CER focus)   [RQ3]         [REQUIRES_USER_INPUT]
PHASE 23 → Decision-log JSONL export + checkpoint↔task_id linking            [RQ1/RQ2]
PHASE 24 → Qualitative metrics (coherence / interpretability / stability)    [RQ1/RQ2]
PHASE 25 → LangGraph production path OR documented deprecation               [REQUIRES_USER_INPUT]
PHASE 26 → Cost / latency / token accounting per session
PHASE 27 → Reproducibility bundle + results-chapter automation (curated only)
PHASE 28 → Hardening (registry error path, parser newline, ThinkingBudget tests)
PHASE 29 → Retrieval-mechanism ablation (keyword vs semantic) + Redis backend  [RQ1] [REQUIRES_USER_INPUT]
```

Each phase keeps the same contract: **Goal → Tasks → Acceptance tests → Commit**. Architecture rules are
unchanged: all data crossing module boundaries is **typed Pydantic v2**; every LLM call goes through the
**Decision Cycle** (`control/cycle.py`) or the bounded `SLMClient`; all FSM transitions stay **pure Python**
(`next_state` takes no LLM call); **no secrets** are ever written to the repo (manifests record provider/model
ids and git SHA, never keys).

> Phases that need real API spend, Docker, or an advisor decision are marked `[REQUIRES_USER_INPUT]`. Their
> CI-checkable acceptance gate is always a `--dry-run` / structural test that validates wiring **without**
> spending budget; the real run is a separate, explicitly-flagged evidence step. **Do not fabricate run
> numbers** — ablation gates assert *valid runs were produced and tabulated*, never a specific SR/CER margin.

---

## PHASE 13 — Run Integrity: API Probe Retry + Run-Level Quality Gate

**Goal:** Eliminate the zero-interaction failure mode that invalidated every B/C run (handoff §7.2, §7.3).
A run where tasks did no work must be flagged `INVALID`, not silently scored `SR=0`.

### Tasks

- `src/framework/orchestration/session.py` — rewrite `validate_slm_api_key()` to retry the `probe_client()`
  call on transient errors (`timeout`, `http_error`, `http_5xx`, SSL/connection) with exponential backoff
  (3 attempts, base 2 s). Return a typed result; on exhaustion raise `ProbeFailedError` *before* the task
  loop so no task records `interaction_count = 0`.

```python
class ProbeResult(BaseModel):
    ok: bool
    attempts: int
    error: str | None

def validate_slm_api_key(max_attempts: int = 3) -> ProbeResult: ...
```

- `eval/run_quality.py` (new) — a deterministic, no-LLM run-level gate over an aggregate JSONL:

```python
class RunQuality(BaseModel):
    run_path: str
    n_tasks: int
    zero_interaction_tasks: int
    valid: bool                 # False if zero_interaction fraction > threshold
    reason: str | None

def assess_run(run_path: str, max_zero_ix_fraction: float = 0.10) -> RunQuality:
    """A run is INVALID if > max_zero_ix_fraction of tasks have interaction_count == 0."""
```

- `eval/run_eval.py` — call `assess_run()` after writing the aggregate JSONL; stamp `"run_valid": bool`
  and `"run_invalid_reason"` into a sidecar `traces/{run}.quality.json`. Print `RUN INVALID: <reason>` to
  stderr and exit non-zero when invalid so batch scripts stop instead of accumulating junk.

### Acceptance tests — `tests/unit/test_run_quality.py`, `tests/unit/test_api_probe_retry.py`

```python
def test_assess_run_flags_all_zero_interaction_as_invalid():
def test_assess_run_passes_when_all_tasks_interacted():
def test_assess_run_threshold_boundary():            # exactly 10% zero-ix → still valid
def test_probe_retries_on_transient_error_then_succeeds(mock_probe):
def test_probe_raises_after_max_attempts(mock_probe): # ProbeFailedError, loop never starts
def test_probe_does_not_retry_on_missing_api_key(mock_probe):  # config error, fail fast
```

### Commit
```
git add -A && git commit -m "phase-13: run integrity (probe retry, run-level zero-interaction quality gate)"
```

---

## PHASE 14 — Eval CLI: Single-Task Rerun + Per-Run Reproducibility Manifest

**Goal:** Make every run reproducible and cheaply re-runnable. Adds `--task-id` (the missing flag noted in
PROGRESS issues) and writes a manifest capturing exactly how a run was produced — no secrets.

### Tasks

- `eval/manifest.py` (new):

```python
class RunManifest(BaseModel):
    run_id: str
    config: str                 # "A" | "B" | "C" | "D"
    dataset: str
    n: int
    seed: int
    provider: str               # from configs/models.yaml active_provider
    planner_profile: str
    executor_profile: str
    git_sha: str                # subprocess: git rev-parse HEAD
    task_ids: list[str]
    ablation_flags: dict        # {memory, control, error_control}
    created_at: datetime
    # NEVER include API keys or env secrets

def write_manifest(run_id: str, **kw) -> Path:   # traces/{run_id}.manifest.json
```

- `eval/run_eval.py` — add `--task-id` (repeatable) that bypasses sampling and runs exactly the named
  task(s) via the existing `_run_single_task`; always emit a `RunManifest` next to the aggregate JSONL.
- Replace the ad-hoc single-task rerun script referenced in PROGRESS with this first-class CLI path.

### Acceptance tests — `tests/unit/test_manifest.py`

```python
def test_manifest_written_with_git_sha_and_no_secrets():   # asserts no "key"/"token" values present
def test_manifest_records_ablation_flags_for_config_D():
def test_run_eval_task_id_runs_only_named_task(monkeypatch):
```

CLI gate (no API key needed):
```
python -m eval.run_eval --config D --dataset humaneval --task-id HumanEval/0 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-14: eval CLI --task-id rerun + per-run reproducibility manifest"
```

---

## PHASE 15 — Measurable Difficulty Slices (HumanEval Hard-Only + Stratified)

**Goal:** Create a task slice on which config A (no memory/control/error-control) does **not** trivially score
100%, so the framework's contribution becomes measurable. This is the precondition for any valid D>A claim.

### Tasks

- `eval/datasets/humaneval_adapter.py` — add a **deterministic** difficulty label (no LLM) so the slice is
  reproducible:

```python
def difficulty_of(task: HumanEvalTask) -> Literal["easy","medium","hard"]:
    """
    Deterministic heuristic from the prompt itself:
      - hard   if prompt_loc > 12 OR n_assertions >= 8 OR contains nested-loop / DP keywords
      - medium if prompt_loc in 6..12 OR n_assertions in 4..7
      - easy   otherwise
    Plus an explicit curated override list configs/humaneval_hard_ids.txt.
    """

def load_humaneval(n=50, seed=42, difficulty: str | None = None) -> list[HumanEvalTask]:
    """difficulty='hard' returns only hard tasks; None keeps the existing stratified behaviour."""
```

- `configs/eval.yaml` — add a named dataset alias `humaneval_hard: {difficulty: hard, sample_size: 30, seed: 42}`
  and keep `humaneval` (stratified) unchanged.
- `configs/humaneval_hard_ids.txt` — curated, version-controlled list of HumanEval ids used as the canonical
  hard slice (overrides the heuristic so the thesis slice is frozen and citable).

### Acceptance tests — `tests/unit/test_difficulty_slices.py`

```python
def test_difficulty_is_deterministic_for_fixed_task():
def test_hard_slice_contains_only_hard_tasks():
def test_curated_hard_ids_override_heuristic():
def test_stratified_default_unchanged():           # regression: existing humaneval behaviour intact
```

### Commit
```
git add -A && git commit -m "phase-15: deterministic difficulty labels + curated HumanEval hard slice"
```

---

## PHASE 16 — Controlled Multi-Step Scenarios (Interaction-Length Sweep) [RQ3]

**Goal:** Directly answer **RQ3** — how cumulative error (CER) scales with the number of interactions.
Build synthetic tasks whose required interaction length is a controlled variable, so CER can be plotted
against interaction count. This is where memory + control are expected to keep config D coherent while A
degrades.

### Tasks

- `eval/datasets/synthetic_multistep.py` (new) — generate parametric tasks with a known minimum number of
  dependent edits/sub-tasks `L` (e.g. build module A, then B depending on A, then C calling both; hidden
  tests check the full chain). Each task is fully deterministic given `(L, seed)`.

```python
class MultiStepTask(BaseModel):
    task_id: str
    required_steps: int          # L: controlled interaction length
    prompt: str
    test_code: str
    entry_point: str

def generate_multistep(levels: list[int] = [2,4,6,8], per_level: int = 5, seed: int = 42) -> list[MultiStepTask]:
```

- `eval/scenarios/interaction_length.py` (new):

```python
def run_interaction_length(config: str, levels: list[int], seed: int = 42) -> dict:
    """
    For each L, run config on the L-step tasks via run_full_session.
    Returns {L: {sr, cer, mean_interactions}} and writes a manifested JSONL per L.
    Pure measurement — no claim asserted here.
    """
```

- `--dry-run` builds the task set and validates schemas/test compilation without calling the API.

### Acceptance tests — `tests/unit/test_interaction_length.py`

```python
def test_generated_tasks_are_deterministic():
def test_required_steps_monotonic_with_level():
def test_generated_test_code_compiles():           # py_compile_check on each test_code
def test_run_interaction_length_dry_run_builds_all_levels():
```

CLI gate:
```
python -m eval.scenarios.interaction_length --config D --levels 2,4,6,8 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-16: controlled multi-step scenarios for CER-vs-interaction-length (RQ3)"
```

---

## PHASE 17 — Reflection Wired into REVISE [RQ2/RQ3]

**Goal:** Make the verbal-reflection mechanism (spec'd in `memory/reflection.py` but **never called** in
production — handoff §3, §7.4) actually run on REVISE, so config D exercises error control on retries.
Reflection is part of the RQ2/RQ3 contribution and currently contributes nothing in real runs.

### Tasks

- `src/framework/orchestration/session.py` — on every REVISE transition (both the `control=True` `next_state`
  REVISE path and the simple fallback REVISE), call `write_reflection(...)` and feed the returned text into
  the next Decision Cycle as `last_error`/guidance for the retried subtask. Respect the existing
  `max_reflections_per_subtask` cap from `configs/memory.yaml`.
- Gate reflection behind the **error_control** ablation flag so configs A/C (no error control) do *not* reflect
  — this keeps the ablation honest (reflection is a D-only mechanism).
- The reflection call is a single bounded `SLMClient` call recorded as `DecisionEntry(kind="reflection",
  importance=1.0)`; **no** new FSM transition and **no** LLM inside `next_state`.

### Acceptance tests — `tests/integration/test_reflection_revise.py` (mocked SLM)

```python
def test_reflection_called_on_revise_when_error_control_on(mock_slm, memory):
def test_reflection_not_called_when_error_control_off(mock_slm, memory):   # config A/C
def test_reflection_capped_per_subtask(mock_slm, memory):
def test_reflection_text_feeds_next_attempt_as_guidance(mock_slm, memory):
def test_reflection_recorded_as_decision_entry(mock_slm, memory):
```

### Commit
```
git add -A && git commit -m "phase-17: wire write_reflection into REVISE (error_control-gated)"
```

---

## PHASE 18 — True-SLM Profile + Provider Replication [REQUIRES_USER_INPUT]

**Goal:** Protect the central thesis claim ("acceptable performance **without relying on LLMs**"). Production
ran DeepSeek `deepseek-v4-flash`, which is not clearly an SLM under the thesis's <30B framing (handoff §1).
Add and verify a genuine open-SLM configuration (OpenRouter Qwen2.5-Coder-7B planner + Devstral-Small executor,
the original Phase-0 spec) so the headline ablation can be reported on a true SLM.

> `[REQUIRES_USER_INPUT]` — needs an `OPENROUTER_API_KEY` with budget and confirmation of which model ids the
> committee accepts as "small". The agent must **not** create accounts or write keys to the repo; the user
> provides the key in `.env`.

### Tasks

- `configs/models.yaml` — add/restore verified profiles `qwen2.5-coder-7b-instruct` (point to the **7B** id, not
  the 32B id the handoff flagged) and `devstral-small`, plus a provider block `openrouter`. Add a named bundle
  `slm_small` (planner=Qwen-7B, executor=Devstral-Small) selectable via env `PLANNER_PROFILE`/`EXECUTOR_PROFILE`.
- `src/framework/slm/registry.py` — ensure `client_for_role` resolves the bundle and surfaces a clear error if a
  profile id is missing (see also Phase 28).
- `scripts/smoke_test.py` — accept `--bundle slm_small`; the smoke task (TASK_1) must reach `OUTCOME: solved`
  on the SLM bundle within 5 minutes.

### Acceptance tests — `tests/unit/test_slm_profiles.py` (no API), plus a marked e2e

```python
def test_slm_small_bundle_loads_two_distinct_profiles():
def test_qwen_profile_points_to_7b_id():            # regression on the handoff's 32B bug
def test_provider_block_resolves_openrouter_base_url():
```

Evidence step (needs key/budget):
```
pytest tests/e2e/test_full_session.py -m e2e            # run with PLANNER_PROFILE/EXECUTOR_PROFILE=slm_small
python scripts/smoke_test.py --bundle slm_small         # must print OUTCOME: solved
```

### Commit
```
git add -A && git commit -m "phase-18: verified true-SLM bundle (Qwen-7B + Devstral-Small) for thesis claim"
```

---

## PHASE 19 — Valid Full Ablation A–D (Multi-Seed, Manifested) [REQUIRES_USER_INPUT]

**Goal:** Produce the thesis's core evidence: a *valid* A/B/C/D comparison on a *measurable* slice
(Phase-15 hard HumanEval + Phase-16 multi-step), across multiple seeds, with manifests and the Phase-13
quality gate enforced. Replaces the broken A=D=100% / invalid-B/C situation.

> `[REQUIRES_USER_INPUT]` — API budget. Estimate cost before running: 4 configs × `n` × `seeds` sessions.

### Tasks

- `eval/scenarios/ablation.py` — add `--seeds 41,42,43`, `--dataset humaneval_hard|multistep`, and a
  `--profile-bundle` pass-through. For each `(config, seed)` write a manifested JSONL and run the Phase-13
  quality gate; **abort the whole ablation** if any run is INVALID (no silent junk).
- Extend `AblationResult` with per-config, per-seed `mean`/`std` of SR and CER and a `n_valid_tasks` count.
- `print_comparison_table()` adds `n_valid`, `SR mean±std`, `CER mean±std`, and the feature columns
  (Memory/Control/ErrorControl) already present.

### Acceptance tests

CLI gate (no spend — validates wiring, sampling, manifests, table formatting on stub results):
```
python -m eval.scenarios.ablation --dataset humaneval_hard --seeds 41,42,43 --dry-run
```

`tests/unit/test_ablation_runner.py` (extend):
```python
def test_ablation_aborts_on_invalid_run():
def test_ablation_aggregates_mean_std_across_seeds():
def test_comparison_table_has_feature_and_validity_columns():
```

Honest evidence test — **skips, never fails**, so a null result is documented not faked:
```python
@pytest.mark.e2e
def test_ablation_d_geq_a_on_hard_slice():
    """Run A and D on the hard slice. If D.SR >= A.SR + 5pp AND D.CER < A.CER → pass.
       Otherwise pytest.skip with the observed numbers (record, do not assert a fabricated win)."""
```

### Commit
```
git add -A && git commit -m "phase-19: valid multi-seed A-D ablation on measurable slices + manifests"
```

---

## PHASE 20 — MBPP Ablation + Traces [REQUIRES_USER_INPUT]

**Goal:** Deliver the MBPP evidence the thesis methodology promises (handoff §7.5: code ready, no API results).

> `[REQUIRES_USER_INPUT]` — API budget.

### Tasks

- `eval/datasets/mbpp_adapter.py` — confirm the sanitized MBPP load (`text` + `test_list`) maps cleanly to the
  `run_full_session` task shape; add the same deterministic `difficulty_of` heuristic as Phase 15.
- Run A–D on `mbpp` (n=50, seed=42) through the Phase-19 ablation path; produce manifested JSONL + per-task rows.
- Confirm the Phase-13 quality gate passes (no zero-interaction MBPP runs).

### Acceptance tests

```python
# tests/unit/test_eval_metrics.py / test_eval_paths.py (extend)
def test_mbpp_task_maps_to_session_shape():
def test_mbpp_test_list_compiles_to_pytest():
```

CLI gate (no spend):
```
python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run
```

Evidence step (needs budget):
```
python -m eval.scenarios.ablation --dataset mbpp --seeds 42 --n 50
```

### Commit
```
git add -A && git commit -m "phase-20: MBPP A-D ablation runs + traces"
```

---

## PHASE 21 — SWE-bench Lite Docker Runner [REQUIRES_USER_INPUT]

**Goal:** Replace the SWE-bench placeholder (`test_code = "assert False  # placeholder"`, handoff §4 Phase 10)
with a real per-instance Docker harness, so SWE-bench results reflect actual repository repair.

> `[REQUIRES_USER_INPUT]` — needs Docker available on the host **and** API budget. The agent must not install
> Docker or download untrusted images without the user enabling it.

### Tasks

- `eval/datasets/swebench_adapter.py` — load SWE-bench **lite**, materialize each instance's repo at the base
  commit into a workspace, and expose the gold `FAIL_TO_PASS` / `PASS_TO_PASS` test ids.
- `eval/swe_docker.py` (new) — run the instance's test command inside the official SWE-bench image via the
  Phase-4 sandbox `safe_execute` (allow-list extended with `docker`), parse pass/fail, return a typed
  `TestResult`. Hard timeout per instance; never raise.
- `configs/eval.yaml` — `swebench.docker_required: true`; the adapter raises a clear, skippable error if Docker
  is absent so CI without Docker degrades to skip, not failure.

### Acceptance tests — `tests/unit/test_swebench_docker.py`

```python
def test_swebench_instance_materializes_repo(tmp_path):     # mocked git, no network
def test_swe_docker_skips_cleanly_when_docker_absent(monkeypatch):
def test_swe_result_is_typed_testresult():
```

CLI gate (structural; Docker run is the evidence step):
```
python -m eval.run_eval --config D --dataset swebench --n 1 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-21: SWE-bench lite Docker runner (replaces placeholder tests)"
```

---

## PHASE 22 — Agent-Count Experiment (1 vs 2 Agents, CER Focus) [RQ3] [REQUIRES_USER_INPUT]

**Goal:** Answer the second half of **RQ3** — how the *number of agents* affects cumulative error. Run the
existing `agent_count.py` (Executor-only vs Planner+Executor) on real API, which the handoff notes has never
been run with live calls (§7.5).

> `[REQUIRES_USER_INPUT]` — API budget.

### Tasks

- `eval/scenarios/agent_count.py` — parameterize over the Phase-16 multi-step slice (where coordination load is
  real) and over seeds; for each (`planner_enabled` ∈ {False, True}) report SR, **CER**, mean interactions, and
  contradiction count (from Phase-23 decision logs once available). Write manifested JSONL.
- Ensure the 1-agent path still registers a root subtask so `interaction_count > 0` (guards against the
  zero-interaction artifact).

### Acceptance tests — extend `tests/unit/test_ablation_runner.py`

```python
def test_agent_count_one_agent_disables_planner():
def test_agent_count_two_agent_enables_planner():
def test_agent_count_reports_cer_per_arm():
```

CLI gate:
```
python -m eval.scenarios.agent_count --dataset multistep --dry-run
```

### Commit
```
git add -A && git commit -m "phase-22: agent-count experiment (1 vs 2 agents) CER measurement (RQ3)"
```

---

## PHASE 23 — Decision-Log JSONL Export + Checkpoint↔task_id Linking [RQ1/RQ2]

**Goal:** Fix the qualitative-analysis blocker (handoff §7.6): traces store only `RunResult` summaries in JSONL
while full decision logs live in `traces/checkpoints/*.json` keyed by `sess-*` ids that often don't match
`HumanEval/N`. Without a clean decision stream, RQ1/RQ2 qualitative claims can't be substantiated.

### Tasks

- `src/framework/orchestration/session.py` — alongside the `RunResult` row, stream each committed
  `DecisionEntry` to `traces/decisions/{config}_{dataset}_{run_id}.jsonl`, every line tagged with
  `task_id`, `session_id`, `step_index`, `kind`, `self_check.verdict`.
- Add a stable `task_id ↔ session_id` map written into the run manifest (Phase 14) so checkpoints, decision
  JSONL, and `RunResult` rows all join on `task_id`.
- `scripts/analyze_traces.py` — read decisions from the new JSONL (not only checkpoints); `check_behavioral_
  interpretability(task_id)` resolves via the manifest map.

### Acceptance tests — `tests/unit/test_decision_jsonl.py`, extend `tests/unit/test_analyze_traces.py`

```python
def test_decision_entries_streamed_with_task_id():
def test_manifest_contains_task_to_session_map():
def test_analyze_traces_joins_decisions_on_task_id():
def test_interpretability_dump_resolves_by_humaneval_id():   # the id-mismatch regression
```

### Commit
```
git add -A && git commit -m "phase-23: decision-log JSONL export + task_id<->session linking for qualitative analysis"
```

---

## PHASE 24 — Qualitative Metrics: Coherence / Interpretability / Stability [RQ1/RQ2]

**Goal:** Implement the thesis's qualitative criteria (انسجام تصمیم‌گیری، قابلیت تفسیر، پایداری بلندمدت) as
**deterministic** computations over the Phase-23 decision JSONL, so the qualitative chapter rests on numbers,
not prose.

### Tasks

- `eval/metrics/qualitative.py` (new):

```python
class QualitativeReport(BaseModel):
    contradiction_rate: float        # contradiction self_check issues / total decisions  (coherence, RQ2)
    rationale_coverage: float        # decisions with non-empty rationale / total          (interpretability)
    loop_rate: float                 # loop-flagged decisions / total                      (stability)
    oscillation_index: float         # repeated kind+payload-hash flips over a session     (stability, RQ3)
    by_interaction_length: dict      # metric trajectories vs interaction count            (ties to Phase 16)

def compute_qualitative(decisions_jsonl: str) -> QualitativeReport: ...
```

- `scripts/analyze_traces.py` — add `--qualitative` to emit a per-config `QualitativeReport`; compare A vs D to
  show whether memory/control reduce contradiction and oscillation as interaction length grows.

### Acceptance tests — `tests/unit/test_qualitative_metrics.py`

```python
def test_contradiction_rate_counts_contradiction_issues():
def test_rationale_coverage_full_when_all_have_rationale():
def test_loop_rate_uses_quality_gate_loop_flag():
def test_oscillation_index_detects_flip_flop_decisions():
def test_metrics_bucketed_by_interaction_length():
```

### Commit
```
git add -A && git commit -m "phase-24: deterministic qualitative metrics (coherence, interpretability, stability)"
```

---

## PHASE 25 — LangGraph Production Path OR Documented Deprecation [REQUIRES_USER_INPUT]

**Goal:** Resolve the honesty gap: the thesis presents a LangGraph FSM, but production uses the imperative
loop and `build_graph` runs only in tests with `MemorySaver` (handoff §3, §6). Either make LangGraph the real
path with durable `SqliteSaver` checkpointing, or formally deprecate it and document the imperative loop as the
FSM of record.

> `[REQUIRES_USER_INPUT]` — advisor/committee decision: is LangGraph a load-bearing thesis claim? Pick **Option A**
> (adopt) or **Option B** (deprecate) before implementing.

### Tasks — Option A (adopt LangGraph in production)

- `src/framework/orchestration/graph.py` — switch checkpointer to `SqliteSaver.from_conn_string(config.sqlite_path)`;
  ensure node functions wrap the *same* Planner/Executor Decision-Cycle calls (no logic fork).
- `session.py` — add `run_full_session(..., engine="graph")` that drives the compiled graph; keep `engine="loop"`
  as default until parity is shown. Transitions remain pure-Python `next_state`.

### Tasks — Option B (deprecate)

- Move `graph.py` under `src/framework/orchestration/_experimental/`, add a module docstring stating it is not
  the production path, and add a `docs/fsm_of_record.md` describing the imperative loop as the FSM (states,
  transitions, loop/escalate guards) with a one-paragraph thesis-text justification.

### Acceptance tests

Option A — `tests/integration/test_workflow.py` (extend):
```python
def test_graph_uses_sqlite_saver():
def test_graph_engine_reaches_done_on_passing_task(mock_slm):
def test_graph_and_loop_produce_same_terminal_outcome(mock_slm):   # parity
```
Option B — `tests/unit/test_deprecation.py`:
```python
def test_graph_marked_experimental_not_imported_by_session():
def test_fsm_of_record_doc_exists():
```

### Commit
```
git add -A && git commit -m "phase-25: LangGraph production adoption (SqliteSaver) OR documented deprecation"
```

---

## PHASE 26 — Cost / Latency / Token Accounting per Session

**Goal:** Substantiate the thesis's efficiency argument (SLMs cheaper than LLMs) with measured per-session
tokens, latency, and estimated cost. The `SLMClient` already returns `tokens_used` and `elapsed_ms`; nothing
aggregates them.

### Tasks

- `src/framework/orchestration/session.py` — accumulate `tokens_used` and `elapsed_ms` across all SLM calls in a
  session; add `tokens_total`, `latency_ms_total`, `llm_calls` to `RunResult` (extend the Pydantic model in
  `eval/metrics/sr.py`).
- `eval/metrics/cost.py` (new) — `estimate_cost(run_path, price_table: dict) -> dict`, reading per-model prices
  from `configs/models.yaml` (`price_per_1k_in`/`price_per_1k_out`, defaulting to 0 when unknown). No network.
- `scripts/generate_report.py` — add a cost/latency/token column block to the report.

### Acceptance tests — `tests/unit/test_cost_accounting.py`

```python
def test_run_result_accumulates_tokens_and_latency():
def test_estimate_cost_uses_price_table():
def test_estimate_cost_zero_when_price_unknown():
def test_llm_call_count_recorded_per_session():
```

### Commit
```
git add -A && git commit -m "phase-26: per-session cost/latency/token accounting"
```

---

## PHASE 27 — Reproducibility Bundle + Results-Chapter Automation (Curated Only)

**Goal:** Generate the thesis results tables from **curated** runs only — explicitly excluding the
do-not-cite runs the handoff lists (§5) — so the report can never silently include a 70%/invalid run again.

### Tasks

- `configs/cite_allowlist.yaml` (new) — the canonical run ids to cite (seed list, manifest-verified). The
  report generator reads *only* these unless `--all` is passed.
- `scripts/generate_report.py` — add `--curated` (default for the thesis report): join each cited run to its
  Phase-14 manifest, fail loudly if a cited run is missing its manifest or failed the Phase-13 quality gate,
  and emit SR/CER as `mean ± 95% CI` across the cited seeds (multi-seed CIs).
- Bundle: `scripts/make_repro_bundle.py` (new) — copies cited JSONL + manifests + decision JSONL into
  `artifacts/repro_bundle/` with a `MANIFEST_INDEX.md`; no keys, no full workspaces.

### Acceptance tests — `tests/unit/test_report_curated.py`

```python
def test_curated_report_excludes_non_allowlisted_runs():
def test_report_fails_on_cited_run_missing_manifest():
def test_report_rejects_cited_run_that_failed_quality_gate():
def test_ci_computed_across_seeds():
def test_repro_bundle_contains_no_secrets():
```

CLI gate:
```
python scripts/generate_report.py --curated --dry-run
```

### Commit
```
git add -A && git commit -m "phase-27: curated results-chapter automation + reproducibility bundle"
```

---

## PHASE 28 — Hardening (Registry Error Path, Parser Newline, ThinkingBudget Tests)

**Goal:** Close the latent correctness gaps the handoff flags (§4 Phase 1 risk, §4 Phase 4 parser note, §7.7):
the `registry.py` import bug on a bad profile env, the one missing JSON-repair pattern, and the untested
`ThinkingBudget`.

### Tasks

- `src/framework/slm/registry.py` — remove the fragile `list_profile_names` import from `config`; on an invalid
  `{ROLE}_PROFILE`/bundle, return a typed, actionable error listing valid profile names — never `ImportError`.
- `src/framework/error_control/parser.py` — add the 8th repair pattern (JSON strings containing literal
  newlines) noted as missing; keep it as a pure transform with a focused unit test.
- `src/framework/error_control/thinking.py` — add the unit coverage that Phase 4 omitted (`feed` aborts at
  limit, `reuse_context` returns prior context).

### Acceptance tests

```python
# tests/unit/test_slm_registry.py (extend)
def test_invalid_profile_env_returns_typed_error_not_importerror():
def test_error_lists_valid_profile_names():

# tests/unit/test_error_control.py (extend)
def test_parser_repairs_literal_newline_in_string():

# tests/unit/test_thinking_budget.py (new)
def test_thinking_budget_aborts_at_limit():
def test_thinking_budget_reuse_context_returns_prior():
```

### Commit
```
git add -A && git commit -m "phase-28: hardening (registry error path, parser newline repair, ThinkingBudget tests)"
```

---

## PHASE 29 — Retrieval-Mechanism Ablation + Redis Backend [RQ1] [REQUIRES_USER_INPUT]

**Goal:** Strengthen **RQ1** by testing whether the memory *mechanism* matters: compare the current keyword
Generative-Agents retrieval against a semantic (Chroma) retriever behind a config flag, and complete the
`RedisBackend` (currently `NotImplementedError`) so the persistent-memory backend is more than SQLite.

> `[REQUIRES_USER_INPUT]` — optional; only pursue if the committee wants a memory-mechanism comparison. Chroma is
> already a bootstrap dependency; Redis needs a running server for its tests (otherwise they skip).

### Tasks

- `src/framework/memory/retrieval.py` — add `SemanticRetriever` (sentence-transformers + Chroma) behind
  `memory.yaml: retrieval.mode: keyword|semantic`; the `retrieve_top_k` contract (typed `RetrievalItem`, 150-token
  cap) is unchanged so it drops into the Working-Memory builder without API changes.
- `src/framework/memory/backend.py` — implement `RedisBackend.write/read/query/append` against the
  `memory.yaml` Redis config with the documented 24 h TTL; `create_backend_from_env()` selects it on
  `MEMORY_BACKEND=redis`.
- `eval/scenarios/ablation.py` — add a `retrieval_mode` axis so config B/D can be run keyword vs semantic and
  the SR/CER delta attributed to the retrieval mechanism (RQ1 evidence).

### Acceptance tests

```python
# tests/unit/test_retrieval_semantic.py
def test_semantic_retriever_returns_typed_items_capped_150_tokens():
def test_retrieval_mode_flag_switches_backend():
def test_keyword_mode_is_default_and_unchanged():

# tests/unit/test_redis_backend.py
def test_redis_backend_round_trip_when_server_available():   # pytest.skip if no server
def test_create_backend_from_env_selects_redis():
```

### Commit
```
git add -A && git commit -m "phase-29: retrieval-mechanism ablation (keyword vs semantic) + Redis backend (RQ1)"
```

---

## Test Gates — Phases 13+

```bash
# Before marking any phase DONE, run its gate:
PHASE 13: pytest tests/unit/test_run_quality.py tests/unit/test_api_probe_retry.py
PHASE 14: pytest tests/unit/test_manifest.py && python -m eval.run_eval --config D --dataset humaneval --task-id HumanEval/0 --dry-run
PHASE 15: pytest tests/unit/test_difficulty_slices.py
PHASE 16: pytest tests/unit/test_interaction_length.py && python -m eval.scenarios.interaction_length --config D --levels 2,4,6,8 --dry-run
PHASE 17: pytest tests/integration/test_reflection_revise.py
PHASE 18: pytest tests/unit/test_slm_profiles.py            # + e2e with slm_small bundle (needs key)
PHASE 19: python -m eval.scenarios.ablation --dataset humaneval_hard --seeds 41,42,43 --dry-run && pytest tests/unit/test_ablation_runner.py
PHASE 20: python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run
PHASE 21: pytest tests/unit/test_swebench_docker.py         # + Docker run (needs Docker + key)
PHASE 22: python -m eval.scenarios.agent_count --dataset multistep --dry-run && pytest tests/unit/test_ablation_runner.py
PHASE 23: pytest tests/unit/test_decision_jsonl.py tests/unit/test_analyze_traces.py
PHASE 24: pytest tests/unit/test_qualitative_metrics.py
PHASE 25: pytest tests/integration/test_workflow.py          # Option A; or tests/unit/test_deprecation.py for Option B
PHASE 26: pytest tests/unit/test_cost_accounting.py
PHASE 27: pytest tests/unit/test_report_curated.py && python scripts/generate_report.py --curated --dry-run
PHASE 28: pytest tests/unit/test_slm_registry.py tests/unit/test_error_control.py tests/unit/test_thinking_budget.py
PHASE 29: pytest tests/unit/test_retrieval_semantic.py tests/unit/test_redis_backend.py
```

> **Dependency order:** 13 → 14 → 15 → 16 unblock everything else. 17 must land before 19 (so config D
> exercises reflection). 18 should land before 19/20 if the headline ablation is to run on a true SLM. 23
> must land before 24 (qualitative metrics read the decision JSONL) and before 22's contradiction column.
> Phases 25–29 are independent and can be scheduled against the thesis timeline.
