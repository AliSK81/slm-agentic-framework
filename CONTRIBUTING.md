# Contributing to SLM Agentic Framework

Thank you for your interest in contributing! This project is an MSc thesis implementation, and community input is welcome.

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

## Code Style

- Follow existing code conventions (Python 3.11+, type hints, Pydantic models).
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
