"""Backward-compatible re-exports; prefer ``framework.slm.config``."""

from __future__ import annotations

from framework.slm.config import (
    active_provider_name,
    api_key_env_var_for_active_provider,
    api_key_for_active_provider,
)

# Legacy names used by older call sites
slm_provider = active_provider_name
api_key_env_var = api_key_env_var_for_active_provider
api_key = api_key_for_active_provider


def base_url() -> str:
    """Base URL for the active provider."""
    from framework.slm.config import load_provider, resolve_base_url

    return resolve_base_url(load_provider(active_provider_name()))


def uses_openrouter_headers() -> bool:
    """Deprecated; headers come from yaml ``providers.*.headers``."""
    from framework.slm.config import load_provider

    spec = load_provider(active_provider_name())
    return "HTTP-Referer" in spec.headers
