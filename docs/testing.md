# Testing Guide

## Test Categories

- `tests/unit/`: fast tests with fixtures and mocks
- `tests/integration/`: integration behavior without live external APIs
- `tests/e2e/`: end-to-end tests that require a live SLM provider

## Common Commands

```bash
# Unit + integration
pytest tests/ -m "not e2e" -v

# e2e only
pytest tests/ -m e2e -v
```

## Notes

- e2e tests are marked with `@pytest.mark.e2e`
- run non-e2e checks before opening a pull request
