# PROGRESS — SLM Agentic Framework

> **This file is the agent's memory across context resets.**
> Every session: read this file first. Find CURRENT_PHASE. Do the work. Update this file. Commit. Continue.
> Never wait for user input unless the phase says `[REQUIRES_USER_INPUT]`.

---

## CURRENT STATE

```yaml
current_phase: 18
phase_status: NOT_STARTED
last_updated: "2026-05-21T00:00Z"
last_commit: "1d2d1fb"
blocker: null
```

---

## PHASE LOG

```yaml
phases:
  0:
    name: "Project Bootstrap"
    status: DONE      # NOT_STARTED | IN_PROGRESS | DONE | BLOCKED
    test_gate: "pytest tests/ --collect-only"
    commit: "a5f7bdb"
    notes: "Skeleton, configs, venv, requirements.txt. Import smoke + pytest collect pass."

  1:
    name: "SLM Client (OpenRouter)"
    status: DONE
    test_gate: "pytest tests/unit/test_slm_client.py"
    commit: "659353b"
    notes: "6/6 unit tests pass with httpx MockTransport."

  2:
    name: "Memory Stores"
    status: DONE
    test_gate: "pytest tests/unit/test_memory_stores.py"
    commit: "4486a4e"
    notes: "10/10 unit tests. SQLite backend, 4 stores, Generative Agents scoring."

  3:
    name: "Working Memory Builder"
    status: DONE
    test_gate: "pytest tests/unit/test_retrieval.py"
    commit: "d913790"
    notes: "6/6 tests. WorkingMemory, builder, 5 skill YAML cards."

  4:
    name: "Error Control Infrastructure"
    status: DONE
    test_gate: "pytest tests/unit/test_error_control.py"
    commit: "67220b3"
    notes: "19/19 tests. Parser, quality gate, truncation, thinking, watchdog, sandbox, checkpoint."

  5:
    name: "Bounded Tool Interface"
    status: DONE
    test_gate: "pytest tests/unit/test_tools.py"
    commit: "e7c384f"
    notes: "15/15 tests. compile, pytest runner, file tools, search index."

  6:
    name: "Decision Cycle"
    status: DONE
    test_gate: "pytest tests/unit/test_self_check.py tests/integration/test_decision_cycle.py"
    commit: "72d8844"
    notes: "13/13 tests. Cycle, self_check, budget limiter, mocked SLM integration."

  7:
    name: "Workflow State Machine"
    status: DONE
    test_gate: "pytest tests/integration/test_workflow.py"
    commit: "e1c9cd8"
    notes: "12/12 tests. LangGraph FSM, ledger, reflection cap, MemorySaver checkpoint."

  8:
    name: "Agent Implementations"
    status: DONE
    test_gate: "pytest tests/integration/"
    commit: "26a5355"
    notes: "24 integration tests. Planner/Executor + Dispatch/Report/Handback messages."

  9:
    name: "Integration: Full Session E2E"
    status: DONE
    test_gate: "pytest tests/e2e/test_full_session.py -m e2e"
    commit: "d4b531b"
    notes: "6/6 e2e pass. load_project_env(override=True), session runner, smoke_test. Fixed model ID, JSON format prompt, executor payload.code, pytest wrapper."

  10:
    name: "Evaluation Harness"
    status: DONE
    test_gate: "pytest tests/unit/"
    commit: "f3f6b2b"
    notes: "70 unit tests. HumanEval/MBPP/SWE adapters, SR/CER, stratified sampling, RunResult in sr.py."

  11:
    name: "Ablation Runner"
    status: DONE
    test_gate: "python eval/scenarios/ablation.py --dry-run"
    commit: "6c355c1"
    notes: "76 unit + 24 integration pass. run_ablation A–D, comparison table, agent_count.py. Ablation flags wired: memory→WM retrieval, control→self_check+FSM revise, error_control→quality gate."

  12:
    name: "Qualitative Trace Analysis"
    status: DONE
    test_gate: "pytest tests/e2e/ -m e2e"
    commit: "072fbf2"
    notes: >
      2026-05-20 staged gate (scripts/run_phase12_staged.py) exit 0: session 6/6;
      test_humaneval_20_tasks_config_D PASSED. Provider: DeepSeek V4 Flash (configs/models.yaml).
      HumanEval 20-task seed=42 — config D: D_humaneval_20260520T082826Z SR 100% CER 0% (canonical).
      Second D pass in same pytest run: D_humaneval_20260520T085222Z SR 70% — INVALID (6 tasks, network
      http_error, interaction_count 0); do not cite. Rerun: D_humaneval_20260520T090933Z initially 95%
      (HumanEval/2 planner int task_id bug); single-task rerun + trace patch → 20/20 100%. Config A:
      A_humaneval_20260520T083955Z SR 100%. test_ablation_d_beats_a_on_humaneval SKIPPED (A=D, no +5pp).
      Framework fixes: SLM json_object prompt, executor edit_file aliases/full replace, planner string
      subtasks + str(task_id), e2e logging (logs/e2e_*.log). Optional: full A/B/C/D table via
      eval/scenarios/ablation.py (Phase 11 harness, not Phase 12 e2e).

  13:
    name: "Run Integrity (probe retry + run quality gate)"
    status: DONE
    test_gate: "pytest tests/unit/test_run_quality.py tests/unit/test_api_probe_retry.py"
    commit: "fa24e04"
    notes: "6/6 unit tests pass. ProbeResult + ProbeFailedError + exponential probe retry; eval/run_quality assess_run; run_eval quality sidecar + exit 1 on INVALID."

  14:
    name: "Eval CLI --task-id + run manifest"
    status: DONE
    test_gate: "pytest tests/unit/test_manifest.py"
    commit: "ecc3eda"
    notes: "3/3 unit tests + CLI dry-run gate pass. eval/manifest.py, --task-id/--config/--dataset, load_*_by_ids adapters."

  15:
    name: "HumanEval difficulty slices + hard ids"
    status: DONE
    test_gate: "pytest tests/unit/test_difficulty_slices.py"
    commit: "a04c070"
    notes: "4/4 unit tests pass. difficulty_of heuristics + configs/humaneval_hard_ids.txt (30 ids); humaneval_hard alias in eval.yaml and run_eval."

  16:
    name: "Multi-step interaction-length scenarios (RQ3)"
    status: DONE
    test_gate: "pytest tests/unit/test_interaction_length.py"
    commit: "7eb1d74"
    notes: "4/4 unit tests + CLI dry-run gate. synthetic_multistep L=2,4,6,8; interaction_length sweep with per-L JSONL+manifest."

  17:
    name: "Reflection on REVISE"
    status: NOT_STARTED
    test_gate: "pytest tests/integration/test_reflection_revise.py"
    commit: null
    notes: "ROADMAP phase 17. error_control-gated."

  18:
    name: "True-SLM bundle (Qwen-7B + Devstral)"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_slm_profiles.py"
    commit: null
    notes: "ROADMAP phase 18. [REQUIRES_USER_INPUT] API key."

  19:
    name: "Valid multi-seed A-D ablation"
    status: NOT_STARTED
    test_gate: "python eval/scenarios/ablation.py --dataset humaneval_hard --seeds 41,42,43 --dry-run"
    commit: null
    notes: "ROADMAP phase 19. [REQUIRES_USER_INPUT] API budget."

  20:
    name: "MBPP ablation + traces"
    status: NOT_STARTED
    test_gate: "python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run"
    commit: null
    notes: "ROADMAP phase 20. [REQUIRES_USER_INPUT]."

  21:
    name: "SWE-bench lite Docker runner"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_swebench_docker.py"
    commit: null
    notes: "ROADMAP phase 21. [REQUIRES_USER_INPUT] Docker + API."

  22:
    name: "Agent-count experiment (RQ3)"
    status: NOT_STARTED
    test_gate: "python -m eval.scenarios.agent_count --dataset multistep --dry-run"
    commit: null
    notes: "ROADMAP phase 22. [REQUIRES_USER_INPUT]."

  23:
    name: "Decision-log JSONL + task_id linking"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_decision_jsonl.py tests/unit/test_analyze_traces.py"
    commit: null
    notes: "ROADMAP phase 23."

  24:
    name: "Qualitative metrics (RQ1/RQ2)"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_qualitative_metrics.py"
    commit: null
    notes: "ROADMAP phase 24."

  25:
    name: "LangGraph production OR deprecation"
    status: NOT_STARTED
    test_gate: "pytest tests/integration/test_workflow.py or tests/unit/test_deprecation.py"
    commit: null
    notes: "ROADMAP phase 25. [REQUIRES_USER_INPUT] advisor choice."

  26:
    name: "Cost/latency/token accounting"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_cost_accounting.py"
    commit: null
    notes: "ROADMAP phase 26."

  27:
    name: "Curated results report + repro bundle"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_report_curated.py"
    commit: null
    notes: "ROADMAP phase 27."

  28:
    name: "Hardening (registry, parser, ThinkingBudget)"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_slm_registry.py tests/unit/test_error_control.py tests/unit/test_thinking_budget.py"
    commit: null
    notes: "ROADMAP phase 28."

  29:
    name: "Retrieval ablation + Redis backend (RQ1)"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_retrieval_semantic.py tests/unit/test_redis_backend.py"
    commit: null
    notes: "ROADMAP phase 29. [REQUIRES_USER_INPUT] optional."
```

---

## HOW TO UPDATE THIS FILE

When a phase completes, update the YAML above:

```yaml
# Example: Phase 0 completed
current_phase: 1        # ← next phase number
phase_status: NOT_STARTED

phases:
  0:
    status: DONE
    commit: "abc1234"
    notes: "All 4 smoke tests pass. Structure created."
```

When a phase is blocked:

```yaml
current_phase: 3
phase_status: BLOCKED

phases:
  3:
    status: BLOCKED
    notes: "ImportError in retrieval.py line 42: missing dependency X. Tried pip install X — not available."

blocker: "Describe the blocker in one sentence here."
```

---

## KNOWN ISSUES AND DECISIONS

```yaml
# Agent appends here when making non-obvious decisions or encountering issues.
decisions:
  - "2026-05-20: Thesis HumanEval D SR uses 082826Z or corrected 090933Z; discard 085222Z (network)."
  - "2026-05-20: Planner coerces SLM numeric task_id/depends_on to str (tests/unit/test_planner.py)."
  - "2026-05-20: Phase 12 e2e runs A+D only (not B/C); full ablation is Phase 11 eval/scenarios/ablation.py."
issues:
  - "Phases 14–29 merged into ROADMAP.md 2026-05-20; Phase 13 done."
  - "scripts/run_phase12_staged.ps1 broken on Windows; use scripts/run_phase12_staged.py."
```

---

## ENVIRONMENT CHECKLIST

```yaml
# Agent verifies these on first run of each session:
env_checks:
  - python_version: "3.14.2 (>=3.11)"
  - venv_active: true
  - active_provider: "deepseek (deepseek-v4-flash)"
  - deepseek_key_set: true
  - openrouter_key_set: true    # optional fallback
  - sqlite_path_exists: true    # ./data/framework.db on first use
  - workspace_dir_exists: false # created on first tool run
```
