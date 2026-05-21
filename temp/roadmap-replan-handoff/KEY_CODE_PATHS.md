# Key Code Paths

Quick map for implementers after replan.

---

## Interactive turn flow

```
aviona/repl.py
  └─ aviona/session.py :: AvionaSession.run_turn()
       ├─ runtime.py :: anchor, constraints, infer_interactive_max_steps  ← move budget to framework
       ├─ contract.py :: verify_turn()
       └─ framework/orchestration/session.py :: run_turn(interactive=True)
            └─ _run_interactive_executor_turn()
                 ├─ executor.execute_node() → Decision Cycle
                 ├─ self_check, quality gate
                 └─ _synthesize_interactive_user_message()  ← replan target
```

---

## Decision Cycle

```
framework/control/cycle.py :: DecisionCycle.run()
framework/control/self_check.py :: self_check()
framework/error_control/quality.py :: QualityGate
framework/orchestration/executor.py :: ExecutorAgent.execute_node()
```

---

## Terminate contract

```
framework/control/models.py :: parse_terminate_payload()
framework/orchestration/session.py :: _session_user_message_from_decisions()
aviona/turn_io.py :: declared_turn_type()
aviona/render.py :: render_turn_detail()
```

---

## Tools

```
framework/orchestration/executor.py   # list_dir, read_file, shell, code_edit, pytest
framework/tools/file_tools.py       # read/write/edit + write-guard
framework/error_control/sandbox.py  # SAFE_COMMANDS allow-list
aviona/permissions.py               # plan/default/auto overlay
```

---

## Memory / prompts

```
framework/memory/working_memory.py :: WorkingMemoryBuilder
framework/memory/stores.py :: DecisionEntry, MemoryStores
aviona/compaction.py :: history anchor
```

---

## Tests & gates

```
scripts/live_gate.py
scripts/debug_session.py
scripts/test-aviona.ps1
tests/unit/test_aviona_contract_matrix.py
tests/integration/test_interactive_turn.py
tests/aviona/JOURNEYS.md
```

---

## Config

```
configs/models.yaml          # aviona-daily profiles
.env                         # SLM API keys (not in repo)
```

---

## Debug

```
aviona/debug_log.py
~/.aviona/debug/<uuid>.txt
```

Log tags: `[REPL]`, `[INTERACTIVE]`, `[CYCLE]`, `[SELF_CHECK]`, `[EXECUTOR]`, `[API RESPONSE]`
