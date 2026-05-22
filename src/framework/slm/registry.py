"""Role-based SLM access — callers use planner/executor, not model or provider names."""

from __future__ import annotations

import os
from typing import Any, Literal

from framework.slm.config import (
    load_profile,
    resolve_bundle,
)

AgentRole = Literal["planner", "executor"]


class ProfileResolutionError(ValueError):
    """Raised when a role cannot be mapped to a yaml profile or bundle."""

    def __init__(
        self,
        role: AgentRole,
        candidate: str | None,
        *,
        profile_names: list[str],
        bundle_names: list[str],
    ) -> None:
        self.role = role
        self.candidate = candidate
        self.profile_names = profile_names
        self.bundle_names = bundle_names
        if candidate:
            message = (
                f"No profile matches {role!r} override {candidate!r}. "
                f"Known profiles: {', '.join(profile_names) or '(none)'}; "
                f"known bundles: {', '.join(bundle_names) or '(none)'}."
            )
        else:
            message = (
                f"No profile configured for role {role!r}. "
                "Set defaults in configs/runtime/models.yaml or {ROLE}_PROFILE in .env. "
                f"Known profiles: {', '.join(profile_names) or '(none)'}; "
                f"known bundles: {', '.join(bundle_names) or '(none)'}."
            )
        super().__init__(message)


def _known_profile_names() -> list[str]:
    """Profile keys from models.yaml without importing list helpers from config."""
    from framework.slm.config import _load_raw

    return sorted(_load_raw().get("profiles", {}).keys())


def _known_bundle_names() -> list[str]:
    """Bundle keys from models.yaml."""
    from framework.slm.config import _load_raw

    return sorted(_load_raw().get("bundles", {}).keys())


def resolve_profile_name(role: AgentRole) -> str:
    """Map agent role to a profile key using env overrides then yaml ``defaults``."""
    from framework.slm.config import _load_raw

    env_profile = os.getenv(f"{role.upper()}_PROFILE", "").strip()
    env_model = os.getenv(f"{role.upper()}_MODEL", "").strip()
    for candidate in (env_profile, env_model):
        if not candidate:
            continue
        resolved = _resolve_env_candidate(role, candidate)
        if resolved:
            return resolved
        raise ProfileResolutionError(
            role,
            candidate,
            profile_names=_known_profile_names(),
            bundle_names=_known_bundle_names(),
        )

    defaults: dict[str, str] = _load_raw().get("defaults", {})
    name = defaults.get(role, "").strip()
    profiles = _load_raw().get("profiles", {})
    if name and name in profiles:
        return name

    raise ProfileResolutionError(
        role,
        None,
        profile_names=_known_profile_names(),
        bundle_names=_known_bundle_names(),
    )


def _resolve_env_candidate(role: AgentRole, candidate: str) -> str | None:
    """Map env override to a profile key (bundle name or profile key/model_id)."""
    from framework.slm.config import _load_raw

    bundles: dict[str, Any] = _load_raw().get("bundles", {})
    if candidate in bundles:
        return resolve_bundle(candidate)[role]

    return _match_profile_key(candidate)


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
