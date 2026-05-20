"""Aviona doctor — probe-only connectivity diagnostics."""

from __future__ import annotations

import logging

from framework.orchestration.session import ProbeFailedError, validate_slm_api_key
from framework.slm.config import active_provider_name, api_key_env_var_for_active_provider, load_profile
from framework.slm.registry import resolve_profile_name

logger = logging.getLogger(__name__)


def run_doctor() -> int:
    """Print provider/model and probe the SLM API without starting a session.

    Returns:
        ``0`` when the probe succeeds; ``1`` on missing key, placeholder, or probe failure.
    """
    provider = active_provider_name()
    profile = load_profile(resolve_profile_name("planner"))
    print(f"provider: {provider}")
    print(f"model: {profile.model_id}")
    print(f"api_key_env: {api_key_env_var_for_active_provider()}")

    try:
        result = validate_slm_api_key()
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 1
    except ProbeFailedError as exc:
        detail = exc.result.error or str(exc)
        print(f"probe failed after {exc.result.attempts} attempt(s): {detail}")
        return 1

    print(f"probe: ok ({result.attempts} attempt(s))")
    return 0
