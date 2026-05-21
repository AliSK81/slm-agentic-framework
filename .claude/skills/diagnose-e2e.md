---
name: diagnose-e2e
description: Analyze e2e test logs for per-task wall time, per-model latency (planner vs executor), unique errors, and cross-config comparison. Use after an e2e run completes or mid-run to check progress.
---

# Diagnose E2E Test Timing

Run the diagnostic script against the current e2e log to produce:

1. **Per-task timing table** — wall time, planner latency, executor latency, LLM call count, overhead
2. **Per-config totals** — SR%, avg times, solved/unsolved counts
3. **Unique error summary** — deduplicated warnings/errors with root cause classification

## Instructions

1. Find the most recent e2e log file:
   ```
   ls -t D:/thesis/agentic-ai/logs/e2e_*.log | head -1
   ```

2. Run the diagnostic script:
   ```
   .venv/Scripts/python.exe scripts/diagnose_e2e.py <log_path>
   ```

3. Summarize the output for the user:
   - Which config is slowest and why
   - If executor time dominates (gpt-oss:20b is the bottleneck)  
   - If any tasks failed and why
   - Error trends (timeouts, WM ceiling, etc.)

## Model assignment reference

| Role | Model | Profile | Timeout |
|---|---|---|---|
| Planner | qwen3:4b-instruct | ollama-qwen3-4b-instruct | 120s |
| Executor | gpt-oss:20b | ollama-gpt-oss-20b | 240s |

## Output interpretation

- **Plan column** = time from session start to planner finishing plan_step
- **Exec column** = time from planner finish to executor task completion (includes all retries)
- **#LLM** = total LLM calls (1 planner + N executor)
- **Ovrhd** = wall time minus total LLM latency (framework overhead)
- High Exec time (>200s) with low #LLM → slow single-call inference (large context)
- High Exec time with high #LLM → executor retry cascade (self-check failures)
