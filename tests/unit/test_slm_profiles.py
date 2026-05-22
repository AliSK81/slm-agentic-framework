"""Unit tests for true-SLM profile bundle (no API calls)."""

from __future__ import annotations

import pytest

from framework.slm.config import (
    load_profile,
    load_provider,
    resolve_bundle,
    resolve_endpoint,
)
from framework.slm.registry import resolve_profile_name


def test_slm_small_bundle_loads_two_distinct_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bundle slm_small maps planner and executor to different profile keys."""
    monkeypatch.setenv("PLANNER_PROFILE", "slm_small")
    monkeypatch.setenv("EXECUTOR_PROFILE", "slm_small")

    planner = resolve_profile_name("planner")
    executor = resolve_profile_name("executor")

    assert planner == "qwen2.5-coder-7b-instruct"
    assert executor == "devstral-small"
    assert planner != executor


def test_qwen_profile_points_to_7b_id() -> None:
    """Regression: qwen2.5-coder-7b-instruct must not point at the 32B OpenRouter id."""
    profile = load_profile("qwen2.5-coder-7b-instruct")
    model_id = profile.model_id.lower()

    assert "7b" in model_id
    assert "32b" not in model_id
    assert profile.model_id == "qwen/qwen2.5-coder-7b-instruct"


def test_provider_block_resolves_openrouter_base_url() -> None:
    """OpenRouter provider block resolves to the public API base URL."""
    spec = load_provider("openrouter")
    endpoint = resolve_endpoint("devstral-small")

    assert "openrouter.ai" in spec.base_url
    assert endpoint.provider == "openrouter"
    assert endpoint.base_url.rstrip("/").endswith("/api/v1")


def test_resolve_bundle_rejects_unknown_profile() -> None:
    """Bundle resolution fails clearly when a profile key is missing."""
    with pytest.raises(ValueError, match="Unknown SLM bundle"):
        resolve_bundle("not-a-bundle")


def test_qwen_3b_profile_has_tuned_wm_settings() -> None:
    """Small-model profile raises WM ceiling and disables reflection by default."""
    from framework.slm.config import clear_config_cache

    clear_config_cache()
    profile = load_profile("ollama-qwen2.5-coder-3b")
    assert profile.max_working_memory_tokens == 750
    assert profile.retrieval_top_k == 2
    assert profile.reflection_enabled is False


def test_model_profile_optional_fields_default_safely() -> None:
    """Profiles without new optional fields keep backward-compatible defaults."""
    from framework.slm.config import clear_config_cache

    clear_config_cache()
    profile = load_profile("qwen2.5-coder-7b-instruct")
    assert profile.retrieval_top_k is None
    assert profile.reflection_enabled is True
