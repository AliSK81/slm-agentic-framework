"""Model registry unit tests — role resolution without provider-specific code."""

from __future__ import annotations

import pytest

from framework.slm.registry import (
    ProfileResolutionError,
    client_for_role,
    resolve_profile_name,
)


def test_resolve_profile_name_uses_yaml_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """When env overrides are unset, defaults.planner / defaults.executor apply."""
    monkeypatch.delenv("PLANNER_PROFILE", raising=False)
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("EXECUTOR_PROFILE", raising=False)
    monkeypatch.delenv("EXECUTOR_MODEL", raising=False)
    assert resolve_profile_name("planner") == "ollama-qwen3-4b-instruct"
    assert resolve_profile_name("executor") == "ollama-gpt-oss-20b"


def test_resolve_profile_name_from_env_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """PLANNER_PROFILE selects a profile key from models.yaml."""
    monkeypatch.setenv("PLANNER_PROFILE", "qwen2.5-coder-7b-instruct")
    assert resolve_profile_name("planner") == "qwen2.5-coder-7b-instruct"


def test_client_for_role_returns_client_with_matching_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """client_for_role loads the profile resolved for that role."""
    monkeypatch.delenv("PLANNER_PROFILE", raising=False)
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("EXECUTOR_PROFILE", raising=False)
    monkeypatch.delenv("EXECUTOR_MODEL", raising=False)
    client = client_for_role("executor")
    assert client.profile.model_id == "gpt-oss:20b"
    client.close()


def test_invalid_profile_env_returns_typed_error_not_importerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid PLANNER_PROFILE raises ProfileResolutionError, not ImportError."""
    monkeypatch.setenv("PLANNER_PROFILE", "definitely-not-a-real-profile")
    with pytest.raises(ProfileResolutionError) as exc_info:
        resolve_profile_name("planner")
    assert exc_info.type is ProfileResolutionError
    assert "definitely-not-a-real-profile" in str(exc_info.value)


def test_error_lists_valid_profile_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProfileResolutionError message lists yaml profile keys for debugging."""
    monkeypatch.setenv("EXECUTOR_PROFILE", "no-such-bundle-or-profile")
    with pytest.raises(ProfileResolutionError) as exc_info:
        resolve_profile_name("executor")
    message = str(exc_info.value)
    assert "deepseek-v4-flash" in message
    assert "qwen2.5-coder-7b-instruct" in message
