"""Shared pytest configuration."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from framework.env import load_project_env
from framework.runtime_dirs import logs_dir

_E2E_LOGGING_READY = False
_E2E_LOG_PATH: Path | None = None


def _configure_e2e_logging() -> Path:
    """Send framework/eval logs to a timestamped file and the console."""
    global _E2E_LOGGING_READY, _E2E_LOG_PATH
    if _E2E_LOGGING_READY and _E2E_LOG_PATH is not None:
        return _E2E_LOG_PATH

    log_dir = logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    _E2E_LOG_PATH = log_dir / f"e2e_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.log"

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(_E2E_LOG_PATH, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    for name in ("framework", "eval"):
        log = logging.getLogger(name)
        log.setLevel(logging.INFO)
        log.handlers.clear()
        log.addHandler(file_handler)
        log.addHandler(stream_handler)
        log.propagate = False

    _E2E_LOGGING_READY = True
    return _E2E_LOG_PATH


def pytest_configure(config: pytest.Config) -> None:
    load_project_env()
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end tests that call the real SLM API",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Print log path when the collected suite includes e2e tests."""
    if any(item.get_closest_marker("e2e") for item in items):
        log_path = _configure_e2e_logging()
        print(f"\nE2E logs: {log_path}\n", file=sys.stderr)


@pytest.fixture(autouse=True)
def _e2e_file_logging(request: pytest.FixtureRequest) -> None:
    """Attach file logging at test start (pytest may reset handlers after collection)."""
    if request.node.get_closest_marker("e2e") is None:
        return
    _configure_e2e_logging()


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
        pytest.skip(str(exc))  # includes ProbeFailedError

    probe = probe_client().call(
        [{"role": "user", "content": "ping"}],
        role="executor",
        json_mode=False,
    )
    if probe.error:
        if "402" in probe.error or probe.error == "http_402":
            pytest.skip("API credits exhausted (HTTP 402)")
        if probe.error in ("timeout", "http_500", "http_502", "http_503", "http_504", "http_error"):
            pytest.skip(f"SLM API unavailable ({probe.error}); retry when provider is stable")

    return key
