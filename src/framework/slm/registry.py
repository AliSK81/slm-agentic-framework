"""Role-based SLM access — callers use planner/executor, not model or provider names."""

from __future__ import annotations

import os
from typing import Any, Literal

from framework.slm.config import (
    ModelProfile,
    active_provider_name,
    load_profile,
    resolve_endpoint,
)

AgentRole = Literal["planner", "executor"]


def resolve_profile_name(role: AgentRole) -> str:
    """Map agent role to a profile key using env overrides then yaml ``defaults``."""
    from framework.slm.config import _load_raw

    env_profile = os.getenv(f"{role.upper()}_PROFILE", "").strip()
    env_model = os.getenv(f"{role.upper()}_MODEL", "").strip()
    for candidate in (env_profile, env_model):
        if not candidate:
            continue
        matched = _match_profile_key(candidate)
        if matched:
            return matched
        from framework.slm.config import list_profile_names

        raise ValueError(
            f"No profile matches {role!r} override {candidate!r}. "
            f"Known profiles: {', '.join(list_profile_names())}"
        )

    defaults: dict[str, str] = _load_raw().get("defaults", {})
    name = defaults.get(role, "").strip()
    profiles = _load_raw().get("profiles", {})
    if name and name in profiles:
        return name

    raise ValueError(
        f"No profile configured for role {role!r}. "
        "Set defaults in configs/models.yaml or {ROLE}_PROFILE in .env."
    )


def _match_profile_key(value: str) -> str | None:
    """Resolve env value to a profile key (by key or by ``model_id``)."""
    from framework.slm.config import _load_raw

    profiles: dict[str, Any] = _load_raw().get("profiles", {})
    if value in profiles:
        return value
    for name, cfg in profiles.items():
        model_id = cfg.get("model_id") or cfg.get("openrouter_id")
        if model_id == value:
            return name
    return None


def list_profile_names() -> list[str]:
    """Profile keys defined in models.yaml."""
    from framework.slm.config import _load_raw

    return list(_load_raw().get("profiles", {}).keys())


def model_id_for_role(role: AgentRole) -> str:
    """API model id for a role (logging / probes)."""
    return load_profile(resolve_profile_name(role)).model_id


def client_for_role(
    role: AgentRole,
    *,
    http_client: Any | None = None,
) -> Any:
    """SLM client for ``planner`` or ``executor`` — no model or provider in call sites."""
    from framework.slm.client import SLMClient

    return SLMClient(resolve_profile_name(role), http_client=http_client)


def probe_client() -> Any:
    """Client for connectivity checks (uses planner role profile)."""
    return client_for_role("planner")
