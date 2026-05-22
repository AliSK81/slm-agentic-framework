# Contributing to SLM Agentic Framework

Thank you for your interest in contributing! Community input is welcome.

## Getting Started

1. **Fork** the repository and clone your fork.
2. Create a **feature branch**: `git checkout -b feat/your-feature`
3. Set up your environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env        # fill in your API keys
   ```
4. Make your changes and add tests where appropriate.
5. Run the test suite: `pytest tests/ -m "not e2e" -v`
6. Commit using clear, descriptive messages.
7. Open a **Pull Request** against `master`.

## Development Standards

- Python version: **3.12+**.
- Keep type hints on public functions and data models.
- Prefer typed Pydantic models for cross-module data contracts.
- Avoid broad exception handling; catch specific exceptions.
- Keep module boundaries clear:
  - `src/framework`: runtime framework
  - `eval`: benchmark and ablation harness
  - `scripts`: maintenance and utility scripts

## Local Validation Before PR

Run these checks locally:

```bash
ruff check src/
pytest tests/ -m "not e2e" -v
```

If your change affects live-provider flows, also run:

```bash
pytest tests/ -m e2e -v
```

Test tiers:

- `tests/unit/`: fast tests with fixtures and mocks
- `tests/integration/`: integration behavior without live external APIs
- `tests/e2e/`: end-to-end tests that require a live SLM provider (run with `pytest tests/ -m e2e -v`)

## Code Style

- Follow existing code conventions (Python 3.12+, type hints, Pydantic models).
- Keep functions focused and well-documented.
- Add or update tests for any changed behaviour.

## Reporting Bugs

Open a [GitHub Issue](https://github.com/AliSK81/slm-agentic-framework/issues) with:
- A clear title and description
- Steps to reproduce
- Expected vs. actual behaviour
- Python version and relevant environment details

## Security Vulnerabilities

Please do **not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md) instead.

## Code of Conduct

All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
