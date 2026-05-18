"""SLM config unit tests — provider blocks from yaml only."""

from __future__ import annotations

import pytest

from framework.slm.config import (
    active_provider_name,
    api_key_required,
    clear_config_cache,
    load_provider,
    resolve_endpoint,
)


def test_load_provider_ollama_does_not_require_api_key() -> None:
    """Ollama provider allows empty API key."""
    spec = load_provider("ollama")
    assert api_key_required(spec) is False


def test_resolve_endpoint_uses_profile_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile-level provider overrides active_provider."""
    monkeypatch.setenv("SLM_PROVIDER", "deepseek")
    endpoint = resolve_endpoint("qwen2.5-coder-7b-instruct")
    assert endpoint.provider == "openrouter"
    assert "openrouter.ai" in endpoint.base_url


def test_active_provider_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """SLM_PROVIDER env selects provider key."""
    monkeypatch.setenv("SLM_PROVIDER", "ollama")
    clear_config_cache()
    assert active_provider_name() == "ollama"
    clear_config_cache()
