"""Model registry unit tests — role resolution without provider-specific code."""

from __future__ import annotations

import pytest

from framework.slm.registry import client_for_role, resolve_profile_name


def test_resolve_profile_name_uses_yaml_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """When env overrides are unset, defaults.planner / defaults.executor apply."""
    monkeypatch.delenv("PLANNER_PROFILE", raising=False)
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("EXECUTOR_PROFILE", raising=False)
    monkeypatch.delenv("EXECUTOR_MODEL", raising=False)
    assert resolve_profile_name("planner") == "default"
    assert resolve_profile_name("executor") == "default"


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
    assert client.profile.model_id == "deepseek-v4-flash"  # default profile model_id
    client.close()
