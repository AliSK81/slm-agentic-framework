# SLM Agentic Framework

MSc thesis implementation: an agentic AI programming framework focused on **memory mechanisms** and **control logic** for small language models (SLMs).

## Modules

- **Memory** — typed stores (State, DecisionLog, SubTaskRegistry, ResultStore) and working-memory assembly
- **Control** — Decision Cycle (per LLM call) and workflow state machine (LangGraph)
- **Error control** — deterministic wrappers around LLM calls and tool execution
- **Orchestration** — Planner + Executor agents via typed Pydantic messages

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # add OPENROUTER_API_KEY
```

## Development

- **Progress:** see `PROGRESS.md` for the current phase
- **Specs:** see `ROADMAP.md` for phase-by-phase tasks and test gates

```bash
pytest tests/unit/ -v
pytest tests/ -m "not e2e"
```

## Layout

```
src/framework/   # core library
eval/            # benchmarks and ablation
tests/           # unit, integration, e2e
configs/         # models, memory, eval YAML
```
