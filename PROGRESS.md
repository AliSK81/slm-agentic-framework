# PROGRESS — SLM Agentic Framework

> **This file is the agent's memory across context resets.**
> Every session: read this file first. Find CURRENT_PHASE. Do the work. Update this file. Commit. Continue.
> Never wait for user input unless the phase says `[REQUIRES_USER_INPUT]`.

---

## CURRENT STATE

```yaml
current_phase: 1
phase_status: IN_PROGRESS
last_updated: "2026-05-17"
last_commit: "a5f7bdb"
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
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_slm_client.py"
    commit: null
    notes: null

  2:
    name: "Memory Stores"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_memory_stores.py"
    commit: null
    notes: null

  3:
    name: "Working Memory Builder"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_retrieval.py"
    commit: null
    notes: null

  4:
    name: "Error Control Infrastructure"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_error_control.py"
    commit: null
    notes: null

  5:
    name: "Bounded Tool Interface"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_tools.py"
    commit: null
    notes: null

  6:
    name: "Decision Cycle"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/test_self_check.py tests/integration/test_decision_cycle.py"
    commit: null
    notes: null

  7:
    name: "Workflow State Machine"
    status: NOT_STARTED
    test_gate: "pytest tests/integration/test_workflow.py"
    commit: null
    notes: null

  8:
    name: "Agent Implementations"
    status: NOT_STARTED
    test_gate: "pytest tests/integration/"
    commit: null
    notes: null

  9:
    name: "Integration: Full Session E2E"
    status: NOT_STARTED
    test_gate: "pytest tests/e2e/test_full_session.py -m e2e"
    commit: null
    notes: "[REQUIRES_USER_INPUT: OPENROUTER_API_KEY must be set in .env]"

  10:
    name: "Evaluation Harness"
    status: NOT_STARTED
    test_gate: "pytest tests/unit/"
    commit: null
    notes: null

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
  - openrouter_key_set: false   # user must set OPENROUTER_API_KEY in .env
  - sqlite_path_exists: false   # created in Phase 2
  - workspace_dir_exists: false # created on first tool run
```
