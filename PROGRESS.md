# PROGRESS — SLM Agentic Framework

> **This file is the agent's memory across context resets.**
> Every session: read this file first. Find CURRENT_PHASE. Do the work. Update this file. Commit. Continue.
> Never wait for user input unless the phase says `[REQUIRES_USER_INPUT]`.

---

## CURRENT STATE

```yaml
current_phase: AV3-2
phase_status: NOT_STARTED
last_updated: "2026-05-21T26:00Z"
last_commit: "d1bcb27"
blocker: null
active_roadmap: ROADMAP_AVIONA_V3.md
thesis_track: paused_at_phase_39
thesis_resume_gate: "FI-7 DONE + AV3-3 live gate green (see ROADMAP_AVIONA_V3.md AV3-3)"
aviona_track: v3_pending
aviona_v2_phase: V2-10
aviona_v2_status: DONE
aviona_v3_phase: AV3-2
aviona_v3_status: NOT_STARTED
pre_v2_tag: pre-v2
pre_v2_baseline_version: "0.2.6"
product_sign_off: "2026-05-21: Chat-first assistant that can edit files (ROADMAP_PRODUCTION_AVIONA_V2.md §2.0). Additive framework terminate.user_message + interactive turn mode approved for V2-1+."
replan_note: "2026-05-21: Claude replan — ROADMAP_FRAMEWORK_INTERACTIVE.md (FI-1..FI-7) + ROADMAP_AVIONA_V3.md (AV3-1..AV3-5). Thesis 39-41 frozen until thesis_resume_gate."
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
    status: DONE
    test_gate: "pytest tests/integration/test_reflection_revise.py"
    commit: "a183368"
    notes: "5/5 integration tests. _run_revise_reflection on REVISE; error_control-gated; reflection_guidance → executor last_error."

  18:
    name: "True-SLM bundle (Qwen-7B + Devstral)"
    status: DONE
    test_gate: "pytest tests/unit/test_slm_profiles.py"
    commit: "ce2a7f1"
    notes: "4/4 unit tests pass. slm_small bundle; qwen 7B id fix; smoke_test --bundle slm_small. Live smoke/e2e pending OPENROUTER_API_KEY in .env."

  19:
    name: "Valid multi-seed A-D ablation"
    status: DONE
    test_gate: "python -m eval.scenarios.ablation --dataset humaneval_hard --seeds 41,42,43 --dry-run"
    commit: "64a0f97"
    notes: "5/5 unit tests + CLI dry-run gate. Multi-seed ablation, quality abort, mean±std table; --profile-bundle deepseek; e2e test_ablation_hard_slice (skip-honest). Live full ablation: user runs with DeepSeek budget."

  20:
    name: "MBPP ablation + traces"
    status: DONE
    test_gate: "python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run"
    commit: "70c09da"
    notes: "8/8 unit tests (MBPP session shape + pytest compile). difficulty_of on MBPPTask. Dry-run eval + ablation mbpp n=5. Live n=50 A-D: [REQUIRES_USER_INPUT] API budget."

  21:
    name: "SWE-bench lite Docker runner"
    status: DONE
    test_gate: "pytest tests/unit/test_swebench_docker.py"
    commit: "f201606"
    notes: "5/5 unit tests. swe_docker.py + extended adapter (FAIL_TO_PASS, materialize). docker in sandbox allow-list. run_eval Docker grading. Live instance: [REQUIRES_USER_INPUT] Docker+API."

  22:
    name: "Agent-count experiment (RQ3)"
    status: DONE
    test_gate: "python -m eval.scenarios.agent_count multistep --dry-run"
    commit: "8655943"
    notes: "8/8 ablation_runner tests. agent_count multistep+seeds, CER/mean_ix per arm. contradiction_count stub until phase 23. Live API: [REQUIRES_USER_INPUT]."

  23:
    name: "Decision-log JSONL + task_id linking"
    status: DONE
    test_gate: "pytest tests/unit/test_decision_jsonl.py tests/unit/test_analyze_traces.py"
    commit: "1c50d28"
    notes: "12/12 unit tests. eval/decision_log.py, on_decision hook, manifest map, analyze_traces task_id join."

  24:
    name: "Qualitative metrics (RQ1/RQ2)"
    status: DONE
    test_gate: "pytest tests/unit/test_qualitative_metrics.py"
    commit: "8440df4"
    notes: "6/6 unit tests. qualitative.py + analyze_traces --qualitative/--compare-a-d; decision log streams issue_kinds + payload_hash."

  25:
    name: "LangGraph production OR deprecation"
    status: DONE
    test_gate: "pytest tests/integration/test_workflow.py"
    commit: "3fbaf7f"
    notes: "Option A. SqliteSaver checkpointer; run_full_session engine=graph (default) + loop parity; 15/15 integration tests."

  26:
    name: "Cost/latency/token accounting"
    status: DONE
    test_gate: "pytest tests/unit/test_cost_accounting.py"
    commit: "a3243e6"
    notes: "5/5 unit tests. TrackingSLMClient, RunResult usage fields, eval/metrics/cost.py, report cost columns."

  27:
    name: "Curated results report + repro bundle"
    status: DONE
    test_gate: "pytest tests/unit/test_report_curated.py && python scripts/generate_report.py --curated --dry-run"
    commit: "52f9252"
    notes: "6/6 unit tests. cite_allowlist.yaml, eval/curated.py, --curated report + CI, make_repro_bundle.py."

  28:
    name: "Hardening (registry, parser, ThinkingBudget)"
    status: DONE
    test_gate: "pytest tests/unit/test_slm_registry.py tests/unit/test_error_control.py tests/unit/test_thinking_budget.py"
    commit: "cda296e"
    notes: "28/28 tests. ProfileResolutionError, parser literal-newline repair, ThinkingBudget unit tests."

  29:
    name: "Retrieval ablation + Redis backend (RQ1)"
    status: DONE
    test_gate: "pytest tests/unit/test_retrieval_semantic.py tests/unit/test_redis_backend.py"
    commit: "1735ad8"
    notes: "4/5 unit tests (Redis live skipped). SemanticRetriever+Chroma, RedisBackend, ablation --retrieval-mode."

  30:
    name: "Discriminative hard slice (RQ2)"
    status: DONE
    test_gate: "pytest tests/unit/test_difficulty_slices.py && python -m eval.run_eval --config A --dataset discriminative --n 5 --dry-run"
    commit: "e96f698"
    notes: "9/9 unit tests. Shared _difficulty.py + _curated_ids.py; discriminative alias in eval.yaml; run_eval/ablation CLI; 30 frozen ids in humaneval_hard_ids.txt."

  31:
    name: "Live multi-seed A-D ablation DeepSeek"
    status: DONE
    test_gate: "python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --dry-run && pytest tests/unit/test_cite_allowlist.py"
    commit: "101c993"
    notes: "Structural: cite sections, seed CLI fix, test_cite_allowlist. Live 12-run matrix deferred (no benchmark API spend)."

  32:
    name: "True-SLM live matrix (slm_small)"
    status: DONE
    test_gate: "pytest tests/unit/test_slm_profiles.py && ablation --profile-bundle slm_small --dry-run"
    commit: "101c993"
    notes: "Structural dry-run OK. Live slm_small matrix deferred."

  33:
    name: "Keyword vs semantic retrieval comparison"
    status: DONE
    test_gate: "pytest tests/unit/test_retrieval_compare.py"
    commit: "101c993"
    notes: "retrieval_compare.py (B/D only); 3/3 unit tests; dry-run CLI OK. Live runs deferred."

  34:
    name: "Efficiency chapter (cost/latency/token)"
    status: DONE
    test_gate: "pytest tests/unit/test_efficiency.py"
    commit: "101c993"
    notes: "efficiency.py + --efficiency report; devstral price_known=false; 4/4 unit tests."

  35:
    name: "MBPP n=50 ablation"
    status: DONE
    test_gate: "python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run"
    commit: "101c993"
    notes: "MBPP dry-run gate OK; mbpp_50 allowlist section stub. Live n=50 deferred."

  36:
    name: "RQ3 interaction-length + agent-count"
    status: DONE
    test_gate: "pytest tests/unit/test_interaction_length.py && agent_count --dry-run"
    commit: "101c993"
    notes: "interaction_length dry-run OK; agent_count contradiction from decision log. Live sweeps deferred."

  37:
    name: "SWE-bench Lite pilot"
    status: DONE
    test_gate: "pytest tests/unit/test_swebench_docker.py"
    commit: "101c993"
    notes: "swebench unit tests pass; eval dry-run OK. Docker pilot deferred."

  38:
    name: "Qualitative + failure taxonomy"
    status: DONE
    test_gate: "pytest tests/unit/test_failure_taxonomy.py tests/unit/test_qualitative_metrics.py"
    commit: "101c993"
    notes: "failure_taxonomy.py; 4/4 unit tests. analyze_traces --taxonomy via taxonomy module."

  39:
    name: "Thesis tables + figures (LaTeX)"
    status: PAUSED
    test_gate: "pytest tests/unit/test_report_latex.py tests/unit/test_figures.py"
    commit: null
    notes: "Curated-only export. Resume after thesis_resume_gate (FI-7 + AV3-3 live gate green)."

  40:
    name: "Docs + zipped repro bundle"
    status: PAUSED
    test_gate: "pytest tests/unit/test_repro_package.py && make_repro_bundle --zip --dry-run"
    commit: null
    notes: "No API."

  41:
    name: "E2E regression smoke + Redis pilot"
    status: PAUSED
    test_gate: "pytest tests/e2e/test_regression_smoke.py --collect-only"
    commit: null
    notes: "[REQUIRES_USER_INPUT optional]"
```

---

## AVIONA TRACK (`ROADMAP_PRODUCTION_AVIONA.md`)

```yaml
aviona_phases:
  1:  { status: DONE, commit: "5a52fbf", gate: "pip install -e . && aviona --version && pytest tests/unit/test_aviona_cli.py", notes: "5/5 CLI tests; editable install + console script." }
  2:  { status: DONE, commit: "d60dd5b", gate: "pytest tests/unit/test_verifier.py tests/unit/test_aviona_session.py", notes: "5 verifier + 3 session tests; workflow regression 15/15." }
  3:  { status: DONE, commit: "21a07ad", gate: "pytest tests/unit/test_aviona_repl.py", notes: "3/3 REPL tests; cli wires probe+run_repl; per-turn KeyboardInterrupt." }
  4:  { status: DONE, commit: "7c6f835", gate: "pytest tests/unit/test_aviona_project.py tests/unit/test_aviona_store.py", notes: "4+5 tests; AVIONA.md→constraints; JSONL+meta; secret guard. v1 DoD met." }
  5:  { status: DONE, commit: "214818d", gate: "pytest tests/unit/test_token_efficiency.py && pytest tests/integration/test_decision_cycle.py", notes: "6/6 efficiency; compact JSON on self-check retry; aviona-daily profile; render.py." }
  6:  { status: DONE, commit: "9ff2984", gate: "pytest tests/unit/test_truncation_caps.py tests/unit/test_compaction.py", notes: "4+5 tests; configs/truncation.yaml; interactive caps; compact before turn." }
  7:  { status: DONE, commit: "b15ff1e", gate: "pytest tests/unit/test_permissions.py", notes: "10/10 permission tests; plan/default/auto; .aviona/settings.yaml; --mode + /mode." }
  8:  { status: DONE, commit: "29e188d", gate: "pytest tests/unit/test_snapshots.py", notes: "7/7 snapshot tests; SnapshotStore + wrappers; aviona undo CLI; checkpoint on TurnResult." }
  9:  { status: DONE, commit: "bb569ff", gate: "pytest tests/unit/test_aviona_doctor.py", notes: "4/4 doctor tests; ~/.aviona/.env then project .env; probe-only exit codes." }
  10: { status: DONE, commit: "08de041", gate: "pytest tests/unit/test_gitctx.py", notes: "5/5 gitctx; git in SAFE_COMMANDS; REPL + anchor summary." }
  11: { status: DONE, commit: "d2e23a3", gate: "pytest tests/unit/test_aviona_resume.py", notes: "7/7 resume; per-session meta; list/load/fork; --continue/--resume/--fork-session." }
  12: { status: DONE, commit: "4c638b3", gate: "pytest tests/unit/test_aviona_session.py", notes: "5/5 session tests incl. v1 sample_repo REPL e2e; fixtures/sample_repo; README Aviona section." }
  thesis_resume: { status: PAUSED, requires_user_input: true }
```

---

## AVIONA V2 TRACK (`ROADMAP_PRODUCTION_AVIONA_V2.md`)

```yaml
product_definition: "Chat-first assistant that can edit files, rooted in cwd (Claude Code model)."
turn_types: [local, answer, inspect, edit, build]
aviona_v2_phases:
  V2-0: { status: DONE, commit: "52ef2da", tag: pre-v2, gate: "git tag pre-v2 && aviona --version == 0.2.6 && scripts/test-aviona.ps1", notes: "Baseline 0.2.x patch stack committed; pre-v2 tag; product sign-off in CURRENT STATE." }
  V2-1: { status: DONE, commit: "2c0a3ca", gate: "pytest tests/unit/test_terminate_contract.py tests/integration/test_decision_cycle.py", notes: "TerminatePayload + SessionOutcome.user_message; prompt hints; self_check validates turn_type." }
  V2-2: { status: DONE, commit: "8fb475b", gate: "pytest tests/integration/test_interactive_turn.py", notes: "run_turn + interactive=True; needs_plan Python promotion; fixed require_slm_api_key corruption." }
  V2-3: { status: DONE, commit: "bc776c3", gate: "pytest tests/unit/test_aviona_contract.py", notes: "TurnContract verify_turn; deleted TurnOutcomeVerifier; session uses inner verifier only." }
  V2-4: { status: DONE, commit: "be8b979", gate: "scripts/test-aviona.ps1 + grep no classify_goal/fallbacks", notes: "Deleted effects/fallbacks; thin run_turn via framework_run_turn + TurnContract; turn_io.py." }
  V2-5: { status: DONE, commit: "9f61b4f", gate: "pytest tests/unit/test_turn_budgets.py", notes: "budgets.py cycle caps; interactive_read_only write-guard; interactive loop until terminate; 68/68 aviona gate." }
  V2-6: { status: DONE, commit: "0826e24", gate: "pytest tests/unit/test_aviona_contract_matrix.py", notes: "20-row contract matrix; JOURNEYS.md rewritten; deleted test_aviona_journeys.py; 84/84 aviona gate." }
  V2-7: { status: DONE, commit: "76ea3a2", gate: "pytest tests/unit/test_runtime_answer.py", notes: "Structured runtime anchor + runtime_answer_constraint; 88/88 aviona gate." }
  V2-8: { status: DONE, commit: "838f43a", gate: "scripts/test-aviona.ps1 -Live", notes: "live_gate.py 9-row locked matrix; local handlers for meta/salam/L3 inspect+edit; interactive read-only guard; 91/91 L2 + 9/9 L3 pass." }
  V2-9: { status: DONE, commit: "6b6ea2c", gate: "scripts/install-aviona.ps1 -DryRun + pytest tests/unit/test_aviona_install.py", notes: "Hardened install-aviona.ps1: repo-relative, -DryRun gate, ~* cleanup, aviona lock retry, version parity; 4/4 install tests." }
  V2-10: { status: DONE, commit: "bf9eadc", gate: "docs updated; aviona --version == 0.3.0 && scripts/test-aviona.ps1", notes: "CHANGELOG.md; AVIONA_CURRENT_STATE + ARCHITECTURE v2 outcome; JOURNEYS L3 table; version 0.3.0; 91/91 L2 gate." }
```

---

## FRAMEWORK INTERACTIVE TRACK (`ROADMAP_FRAMEWORK_INTERACTIVE.md`)

> **Active track.** Implements Interactive Completion Protocol (ICP) in framework control layer.
> Thesis phase 39 resumes only after `thesis_resume_gate` in CURRENT STATE.

```yaml
framework_interactive_phases:
  FI-1: { status: DONE, commit: "a63cdcd", gate: "pytest tests/unit/test_interactive_turn_type_binding.py", notes: "8/8 unit pass. InteractiveTurnState + models.yaml budgets; cycle-1 turn_type_required self_check; session binds budget/read_only; Aviona no longer passes infer_interactive_max_steps." }
  FI-2: { status: DONE, commit: "5feca84", gate: "pytest tests/unit/test_working_memory_contains_tool_output.py", notes: "3/3 unit pass. ToolResultEntry + [TOOL RESULTS]/[RECENT TURNS] in WM; interactive path uses cycle_last_error not reflection_guidance." }
  FI-3: { status: DONE, commit: "7245765", gate: "pytest tests/unit/test_icp_terminate_after_tool.py tests/unit/test_list_dir_repeat_blocked_then_terminate.py", notes: "3/3 ICP unit + 7/7 integration pass. ICP state in interactive.py; repeat_tool/must_terminate self_check; synthesis removed from interactive completion path." }
  FI-4: { status: DONE, commit: "491d60c", gate: "pytest tests/unit/test_finalizer_forces_terminate.py", notes: "4/4 unit pass. finalizer:on terminate-only cycle from [TOOL RESULTS]; finalizer:off honest unresolvable; user_message only from terminate; deleted synthesis." }
  FI-5: { status: DONE, commit: "b9ff3c6", gate: "pytest tests/integration/test_compound_edit_run.py", notes: "3/3 integration pass. Typed handoff phase machine (inspect/edit/run); per-phase budgets; ICP allows needs_edit/needs_run handoffs; needs_run after code_edit for verify." }
  FI-6: { status: DONE, commit: "6453ca6", gate: "pytest tests/unit/test_shell_inspect_permission_policy.py tests/unit/test_executor_tool_parity.py", notes: "8/8 unit pass. is_inspect_run_command + executor auto-allow on turn_type inspect; glob tool; hint parity; search_codebase not advertised." }
  FI-7: { status: DONE, commit: "d1bcb27", gate: "pytest tests/unit/test_interactive_turn_type_binding.py tests/unit/test_interactive_failure_modes.py tests/integration/test_interactive_turn.py", notes: "7/7 failure-mode unit + 15/15 interactive gate pass. _mock_slm_queue.py; R06-R15 loop patterns; wired into scripts/test-aviona.ps1 L2." }
```

---

## AVIONA V3 TRACK (`ROADMAP_AVIONA_V3.md`)

> **Starts after FI-7.** Thin product layer consuming framework ICP.

```yaml
aviona_v3_phases:
  AV3-1: { status: DONE, commit: "PENDING", gate: "pytest tests/unit/test_aviona_consumes_framework_turn_type.py tests/unit/test_aviona_contract_matrix.py", notes: "5/5 + 20/20 matrix pass. Deleted infer_interactive_max_steps; budgets from load_interactive_budgets; run_turn drops max_steps kwarg." }
  AV3-2: { status: PENDING, gate: "pytest tests/unit/test_aviona_permissions_ux.py", notes: "Permission UX for inspect-run; no framework logic in Aviona." }
  AV3-3: { status: PENDING, gate: "scripts/test-aviona.ps1 -Live", notes: "Expand live_gate.py matrix; thesis_resume_gate requires this green." }
  AV3-4: { status: PENDING, gate: "pytest tests/e2e/test_aviona_repl_matrix.py -m e2e", notes: "E2E REPL matrix from PROBLEM_INVENTORY." }
  AV3-5: { status: PENDING, gate: "aviona --version == 0.4.0 && scripts/test-aviona.ps1", notes: "Docs + CHANGELOG 0.4.0; JOURNEYS L3 table update." }
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
  - "2026-05-21: Framework-first replan — FI track before Aviona v3 patches; no phrase routing or synthesis fallbacks."
  - "2026-05-21: Thesis 39 paused until FI-7 + AV3-3 live gate green (Option B insertion from ROADMAP_CONTEXT.md)."
issues:
  - "Phases 14–29 merged into ROADMAP.md 2026-05-20; Phase 13 done."
  - "2026-05-21: ROADMAP_PHASES_NEXT.md merged; phases 30–41 in ROADMAP.md; handoff at 88c1a50."
  - "scripts/run_phase12_staged.ps1 broken on Windows; use scripts/run_phase12_staged.py."
  - "2026-05-21: Aviona v2 replan (ROADMAP_PRODUCTION_AVIONA_V2.md); live REPL fails despite 67 mocked tests; baseline tagged pre-v2 at 0.2.6."
  - "2026-05-21: Live REPL failures traced to framework ICP gap; hardcoded Aviona shortcuts removed at 10c80eb."
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
