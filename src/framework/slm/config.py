"""SLM configuration: providers, profiles, and resolved HTTP endpoints."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import AliasChoices, BaseModel, Field

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MODELS_CONFIG = _PROJECT_ROOT / "configs" / "runtime" / "models.yaml"
_PLACEHOLDER_KEYS = frozenset({"", "your_key_here", "changeme"})


class ProviderSpec(BaseModel):
    """OpenAI-compatible API endpoint (Ollama, OpenRouter, DeepSeek, etc.)."""

    base_url: str
    base_url_env: str | None = None
    api_key_env: str | None = None
    api_key_required: bool = True
    headers: dict[str, str] = Field(default_factory=dict)


class EndpointConfig(BaseModel):
    """Resolved connection settings for one profile."""

    provider: str
    base_url: str
    api_key: str
    headers: dict[str, str]
    model_id: str


class ModelProfile(BaseModel):
    """Model capabilities and limits from configs/runtime/models.yaml."""

    model_id: str = Field(validation_alias=AliasChoices("model_id", "openrouter_id"))
    provider: str | None = None
    context_limit: int
    effective_context: int
    thinking_budget: int | None = None
    api_thinking: bool = False
    reasoning_effort: str | None = None
    max_working_memory_tokens: int
    tool_output_caps: dict[str, int]
    skill_budget_tokens: int
    timeout_by_role: dict[str, int]
    tool_call_format: str = "json"
    retrieval_top_k: int | None = None
    reflection_enabled: bool = True


def models_config_path() -> Path:
    """Path to ``configs/runtime/models.yaml``."""
    return _MODELS_CONFIG


def clear_config_cache() -> None:
    """Drop cached yaml (for tests)."""
    _load_raw.cache_clear()


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    """Parse models.yaml once per process."""
    return yaml.safe_load(_MODELS_CONFIG.read_text(encoding="utf-8")) or {}


def active_provider_name() -> str:
    """Active provider key: ``SLM_PROVIDER`` env, else yaml ``active_provider``."""
    explicit = os.getenv("SLM_PROVIDER", "").strip()
    if explicit:
        return explicit
    return str(_load_raw().get("active_provider", "openrouter")).strip()


def load_provider(name: str) -> ProviderSpec:
    """Load a provider block from yaml."""
    providers: dict[str, Any] = _load_raw().get("providers", {})
    if name not in providers:
        known = ", ".join(sorted(providers)) or "(none)"
        raise ValueError(f"Unknown SLM provider {name!r}. Known: {known}")
    return ProviderSpec.model_validate(providers[name])


def provider_for_profile(profile: ModelProfile) -> str:
    """Provider key for a profile (profile override, else active)."""
    return (profile.provider or active_provider_name()).strip()


def resolve_base_url(spec: ProviderSpec) -> str:
    """Base URL from env override or yaml default."""
    if spec.base_url_env:
        override = os.getenv(spec.base_url_env, "").strip()
        if override:
            return override.rstrip("/")
    return spec.base_url.rstrip("/")


def resolve_api_key(spec: ProviderSpec) -> str:
    """API key from env; empty when not required (e.g. local Ollama)."""
    if not spec.api_key_env:
        return ""
    return os.getenv(spec.api_key_env, "").strip()


def api_key_required(spec: ProviderSpec) -> bool:
    """Whether calls must have a non-empty API key."""
    return spec.api_key_required and bool(spec.api_key_env)


def build_headers(spec: ProviderSpec, api_key_value: str) -> dict[str, str]:
    """Merge provider headers with optional Bearer auth."""
    headers = dict(spec.headers)
    headers.setdefault("Content-Type", "application/json")
    if api_key_value:
        headers["Authorization"] = f"Bearer {api_key_value}"
    return headers


def resolve_endpoint(profile_name: str) -> EndpointConfig:
    """Resolve HTTP endpoint + model id for a named profile."""
    profile = load_profile(profile_name)
    provider_name = provider_for_profile(profile)
    spec = load_provider(provider_name)
    key = resolve_api_key(spec)
    return EndpointConfig(
        provider=provider_name,
        base_url=resolve_base_url(spec),
        api_key=key,
        headers=build_headers(spec, key),
        model_id=profile.model_id,
    )


def list_profile_names() -> list[str]:
    """Profile keys defined in ``configs/runtime/models.yaml``."""
    return list(_load_raw().get("profiles", {}).keys())


def list_bundle_names() -> list[str]:
    """Named bundle keys (e.g. ``slm_small``) from models.yaml."""
    return list(_load_raw().get("bundles", {}).keys())


def resolve_bundle(bundle_name: str) -> dict[str, str]:
    """Resolve a named bundle to planner and executor profile keys.

    Inputs:
        bundle_name: Key under ``bundles`` in models.yaml.

    Outputs:
        Dict with ``planner`` and ``executor`` profile keys.

    Side effects:
        None. Raises ``ValueError`` when the bundle or a referenced profile is missing.
    """
    bundles: dict[str, Any] = _load_raw().get("bundles", {})
    if bundle_name not in bundles:
        known = ", ".join(sorted(bundles)) or "(none)"
        raise ValueError(f"Unknown SLM bundle {bundle_name!r}. Known bundles: {known}")

    block = bundles[bundle_name]
    planner = str(block.get("planner", "")).strip()
    executor = str(block.get("executor", "")).strip()
    if not planner or not executor:
        raise ValueError(
            f"Bundle {bundle_name!r} must define non-empty planner and executor profiles"
        )

    profiles = _load_raw().get("profiles", {})
    for role, profile_name in (("planner", planner), ("executor", executor)):
        if profile_name not in profiles:
            known_profiles = ", ".join(sorted(profiles)) or "(none)"
            raise ValueError(
                f"Bundle {bundle_name!r} references unknown profile {profile_name!r} "
                f"for {role}. Known profiles: {known_profiles}"
            )

    return {"planner": planner, "executor": executor}


def load_profile(profile_name: str) -> ModelProfile:
    """Load a profile from models.yaml."""
    profiles: dict[str, Any] = _load_raw().get("profiles", {})
    if profile_name not in profiles:
        known = ", ".join(sorted(profiles)) or "(none)"
        raise ValueError(
            f"Unknown model profile: {profile_name!r}. Known profiles: {known}"
        )
    return ModelProfile.model_validate(profiles[profile_name])


def api_key_env_var_for_active_provider() -> str:
    """Env var name holding the API key for the active provider."""
    spec = load_provider(active_provider_name())
    return spec.api_key_env or "SLM_API_KEY"


def api_key_for_active_provider() -> str:
    """API key for the active provider."""
    return resolve_api_key(load_provider(active_provider_name()))


def api_key_required_for_active_provider() -> bool:
    """Whether the active provider requires an API key."""
    return api_key_required(load_provider(active_provider_name()))
