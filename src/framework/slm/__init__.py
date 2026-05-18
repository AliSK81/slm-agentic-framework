"""SLM client, configuration, and role-based registry."""

from framework.slm.client import SLMClient, SLMResponse
from framework.slm.config import ModelProfile, active_provider_name
from framework.slm.registry import AgentRole, client_for_role, probe_client, resolve_profile_name

__all__ = [
    "AgentRole",
    "ModelProfile",
    "SLMClient",
    "SLMResponse",
    "active_provider_name",
    "client_for_role",
    "probe_client",
    "resolve_profile_name",
]
