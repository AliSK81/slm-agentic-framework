# PROGRESS — SLM Agentic Framework

> **This file is the agent's memory across context resets.**
> Every session: read this file first. Find CURRENT_PHASE. Do the work. Update this file. Commit. Continue.
> Never wait for user input unless the phase says `[REQUIRES_USER_INPUT]`.

---

## CURRENT STATE

```yaml
current_phase: 11
phase_status: NOT_STARTED
last_updated: "2026-05-17"
last_commit: "f3f6b2b"
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
    status: NOT_STARTED
    test_gate: "python eval/scenarios/ablation.py --dry-run"
    commit: null
    notes: null

  12:
    name: "Qualitative Trace Analysis"
    status: NOT_STARTED
    test_gate: "pytest tests/e2e/ -m e2e"
    commit: null
    notes: "[REQUIRES_USER_INPUT: OPENROUTER_API_KEY must be set in .env]"
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
decisions: []
issues: []
```

---

## ENVIRONMENT CHECKLIST

```yaml
# Agent verifies these on first run of each session:
env_checks:
  - python_version: "3.14.2 (>=3.11)"
  - venv_active: true
  - openrouter_key_set: true
  - sqlite_path_exists: true    # ./data/framework.db on first use
  - workspace_dir_exists: false # created on first tool run
```
