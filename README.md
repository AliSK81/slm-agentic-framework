# SLM Agentic Framework

[![CI](https://github.com/AliSK81/slm-agentic-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/AliSK81/slm-agentic-framework/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

An agentic AI programming framework for **small language models (SLMs)**. The framework provides structured memory mechanisms, decision-cycle control logic, and a multi-agent orchestration layer optimized for resource-constrained models (3B–20B parameters).

---

## Features

- **Typed Memory Stores** — State, DecisionLog, SubTaskRegistry, and ResultStore with working-memory assembly
- **Decision Cycle** — per-LLM-call control logic with deterministic error handling and retry policies
- **Workflow State Machine** — LangGraph-based orchestration for multi-step tasks
- **Multi-Agent Orchestration** — Planner + Executor agents communicating via typed Pydantic messages
- **Provider-agnostic** — `httpx`-based client for Ollama, DeepSeek, OpenRouter, or any OpenAI-compatible endpoint
- **Evaluation harness** — HumanEval, MBPP, SWE-bench adapters and A–D ablation runner

---

## Project Layout

```
src/
  framework/       # core library (memory, control, orchestration, error handling)
eval/              # benchmarks and ablation scripts
tests/             # unit, integration, and e2e test suites
configs/           # YAML configs (runtime/ and reporting/)
scripts/           # smoke checks and reporting utilities
var/               # runtime output (gitignored; traces, logs, checkpoints)
examples/          # minimal usage examples
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- An SLM provider: [Ollama](https://ollama.com) (local, recommended) or an API key for DeepSeek / OpenRouter

### Installation

```bash
git clone https://github.com/AliSK81/slm-agentic-framework.git
cd slm-agentic-framework

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # then edit .env with your provider settings
pip install -e .
```

### Running Tests

```bash
# Unit and integration tests (no API key required)
pytest tests/ -m "not e2e" -v

# Full e2e suite (requires a live SLM endpoint)
pytest tests/ -m e2e -v
```

### Evaluation

```bash
# Dry-run ablation wiring
python -m eval.scenarios.ablation --dataset humaneval_hard --n 10 --seeds 42 --dry-run

# Smoke test (requires live SLM)
python scripts/benchmark/smoke_test.py

# Curated report from trace artifacts
python scripts/reporting/generate_report.py --traces-dir var/traces
```

---

## Configuration

Copy `.env.example` to `.env` and set your preferred provider:

| Variable | Description |
|---|---|
| `SLM_PROVIDER` | Provider key: `ollama`, `deepseek`, `openrouter`, `mohaymen` |
| `PLANNER_PROFILE` | Model profile for the Planner agent (see `configs/runtime/models.yaml`) |
| `EXECUTOR_PROFILE` | Model profile for the Executor agent |
| `MEMORY_BACKEND` | `sqlite` (default) or `redis` |
| `DEFAULT_MAX_STEPS` | Maximum steps per task (default: 20) |

See `configs/runtime/models.yaml` for all available model profiles.

---

## Examples

Run a minimal session (requires a configured SLM provider in `.env`):

```bash
python examples/minimal_session.py
```

---

## Contributing

Contributions, bug reports, and feature suggestions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

