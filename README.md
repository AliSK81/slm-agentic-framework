# SLM Agentic Framework

[![CI](https://github.com/AliSK81/slm-agentic-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/AliSK81/slm-agentic-framework/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

An agentic AI programming framework for **small language models (SLMs)**, developed as an MSc thesis project. The framework provides structured memory mechanisms, decision-cycle control logic, and a multi-agent orchestration layer optimised for resource-constrained models (3B–20B parameters).

---

## Features

- **Typed Memory Stores** — State, DecisionLog, SubTaskRegistry, and ResultStore with working-memory assembly
- **Decision Cycle** — per-LLM-call control logic with deterministic error handling and retry policies
- **Workflow State Machine** — LangGraph-based orchestration for multi-step tasks
- **Multi-Agent Orchestration** — Planner + Executor agents communicating via typed Pydantic messages
- **Provider-agnostic** — works with Ollama, DeepSeek, OpenRouter, or any OpenAI-compatible endpoint
- **Aviona CLI** — terminal coding agent built on top of the framework

---

## Project Layout

```
src/
  framework/       # core library (memory, control, orchestration, error handling)
  aviona/          # Aviona terminal agent built on the framework
eval/              # benchmarks and ablation scripts (HumanEval, MBPP, SWE-bench)
tests/             # unit, integration, and e2e test suites
configs/           # YAML configs for models, memory, and eval
scripts/           # utility and diagnostic scripts
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
```

### Running Tests

```bash
# Unit and integration tests (no API key required)
pytest tests/ -m "not e2e" -v

# Full e2e suite (requires a live SLM endpoint)
pytest tests/ -m e2e -v
```

### Aviona — Terminal Coding Agent

```bash
pip install -e .
cd tests/fixtures/sample_repo   # or any project directory
aviona
> create hello.txt with "hi"
```

Useful Aviona commands:
- `aviona doctor` — probe the configured SLM
- `aviona undo` — restore last snapshotted edits
- `aviona --continue` / `--resume <id>` / `--fork-session`

---

## Configuration

Copy `.env.example` to `.env` and set your preferred provider:

| Variable | Description |
|---|---|
| `SLM_PROVIDER` | Provider key: `ollama`, `deepseek`, `openrouter`, `mohaymen` |
| `PLANNER_PROFILE` | Model profile for the Planner agent (see `configs/models.yaml`) |
| `EXECUTOR_PROFILE` | Model profile for the Executor agent |
| `MEMORY_BACKEND` | `sqlite` (default) or `redis` |
| `DEFAULT_MAX_STEPS` | Maximum steps per task (default: 20) |

See `configs/models.yaml` for all available model profiles.

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [PROGRESS.md](PROGRESS.md) | Current phase and active work |
| [ROADMAP.md](ROADMAP.md) | Thesis phase index |

---

## Contributing

Contributions, bug reports, and feature suggestions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Citation

If you use this framework in your research, please cite:

```bibtex
@misc{ebrahimi2026slm,
  author  = {Ali Ebrahimi},
  title   = {SLM Agentic Framework},
  year    = {2026},
  url     = {https://github.com/AliSK81/slm-agentic-framework}
}
```
