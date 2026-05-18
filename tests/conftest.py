"""Shared pytest configuration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from framework.env import load_project_env


def pytest_configure(config: pytest.Config) -> None:
    load_project_env()
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end tests that call the real SLM API",
    )


@pytest.fixture
def require_api_key() -> str:
    """Skip e2e tests when the SLM API key is missing or invalid."""
    load_project_env()
    from framework.orchestration.session import require_slm_api_key, validate_slm_api_key
    from framework.slm.registry import probe_client

    key = require_slm_api_key()
    try:
        validate_slm_api_key()
    except RuntimeError as exc:
        pytest.skip(str(exc))

    probe = probe_client().call(
        [{"role": "user", "content": "ping"}],
        role="executor",
    )
    if probe.error and ("402" in probe.error or probe.error == "http_402"):
        pytest.skip("API credits exhausted (HTTP 402)")

    return key
