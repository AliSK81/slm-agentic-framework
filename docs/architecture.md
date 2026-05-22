# Architecture Overview

The framework is organized in layered modules:

- `src/framework/memory`: typed memory stores, working-memory assembly, retrieval
- `src/framework/control`: decision cycle, self-check, workflow transitions
- `src/framework/orchestration`: planner/executor coordination and session orchestration
- `src/framework/slm`: provider/client abstractions and model configuration
- `src/framework/tools`: bounded tool interfaces used by agents
- `src/framework/error_control`: parsing, truncation, and safety guards

The evaluation harness lives in `eval/` and consumes the framework as a client.
It is intentionally separated from core runtime code.
