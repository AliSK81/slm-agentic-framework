"""Shared pytest configuration."""

from __future__ import annotations

import pytest

from framework.env import load_project_env


def pytest_configure(config: pytest.Config) -> None:
    load_project_env()
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end tests that call the real OpenRouter API",
    )


@pytest.fixture
def require_api_key() -> str:
    """Skip e2e tests when OPENROUTER_API_KEY is missing or invalid."""
    load_project_env()
    from framework.orchestration.session import (
        require_openrouter_key,
        validate_openrouter_key,
    )

    key = require_openrouter_key()
    try:
        validate_openrouter_key()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    return key
