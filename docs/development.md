# Development Setup

## Requirements

- Python 3.12+
- Virtual environment (`.venv`)

## Local Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

Copy environment defaults:

```bash
cp .env.example .env
```

Then edit `.env` with provider-specific values.

## Recommended Local Checks

```bash
ruff check src/
pytest tests/ -m "not e2e" -v
```
