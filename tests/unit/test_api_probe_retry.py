"""Unit tests for SLM API probe retry in session.validate_slm_api_key."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from framework.orchestration.session import (
    ProbeFailedError,
    ProbeResult,
    validate_slm_api_key,
)
from framework.slm.client import SLMResponse


def _mock_probe_client(monkeypatch: pytest.MonkeyPatch, mock_client: MagicMock) -> None:
    """Patch probe_client to return the given mock."""
    monkeypatch.setattr(
        "framework.orchestration.session.probe_client",
        lambda: mock_client,
    )


def test_probe_retries_on_transient_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient errors retry until the probe succeeds."""
    mock_client = MagicMock()
    mock_client.call.side_effect = [
        SLMResponse(error="timeout"),
        SLMResponse(error="http_error"),
        SLMResponse(content="pong", model="test"),
    ]
    _mock_probe_client(monkeypatch, mock_client)
    monkeypatch.setattr("framework.orchestration.session.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "framework.orchestration.session.api_key_required_for_active_provider",
        lambda: False,
    )

    result = validate_slm_api_key(max_attempts=3, base_delay_s=0.0)

    assert isinstance(result, ProbeResult)
    assert result.ok is True
    assert result.attempts == 3
    assert mock_client.call.call_count == 3
    assert mock_client.close.call_count == 3


def test_probe_raises_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exhausted retries raise ProbeFailedError with attempt count."""
    mock_client = MagicMock()
    mock_client.call.return_value = SLMResponse(error="http_503")
    _mock_probe_client(monkeypatch, mock_client)
    monkeypatch.setattr("framework.orchestration.session.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "framework.orchestration.session.api_key_required_for_active_provider",
        lambda: False,
    )

    with pytest.raises(ProbeFailedError) as exc_info:
        validate_slm_api_key(max_attempts=3, base_delay_s=0.0)

    assert exc_info.value.result.attempts == 3
    assert exc_info.value.result.error == "http_503"
    assert mock_client.call.call_count == 3


def test_probe_does_not_retry_on_missing_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Config errors (missing_api_key) fail fast without retry."""
    mock_client = MagicMock()
    mock_client.call.return_value = SLMResponse(error="missing_api_key")
    _mock_probe_client(monkeypatch, mock_client)
    monkeypatch.setattr(
        "framework.orchestration.session.api_key_required_for_active_provider",
        lambda: False,
    )

    with pytest.raises(ProbeFailedError) as exc_info:
        validate_slm_api_key(max_attempts=3, base_delay_s=0.0)

    assert exc_info.value.result.attempts == 1
    assert mock_client.call.call_count == 1
