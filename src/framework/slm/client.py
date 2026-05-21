"""OpenAI-compatible SLM HTTP client (provider-agnostic)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel

from framework.env import load_project_env
from framework.slm.config import (
    EndpointConfig,
    ModelProfile,
    ProviderSpec,
    api_key_required,
    build_headers,
    load_profile,
    load_provider,
    resolve_api_key,
    resolve_base_url,
    resolve_endpoint,
)

load_project_env()

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE_S = 0.5


def _ensure_json_keyword_in_messages(
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """DeepSeek requires the word 'json' in the prompt when using json_object mode."""
    adjusted: list[dict[str, str]] = []
    for message in messages:
        content = message.get("content", "")
        if "json" not in content.lower():
            content = f"{content}\n\nRespond in json format."
        adjusted.append({**message, "content": content})
    return adjusted


class SLMResponse(BaseModel):
    """Result of a single SLM completion call."""

    content: str = ""
    model: str = ""
    tokens_used: int = 0
    elapsed_ms: int = 0
    error: str | None = None


class SLMClient:
    """Chat client bound to one yaml profile and its resolved provider endpoint."""

    def __init__(
        self,
        profile_name: str,
        *,
        http_client: httpx.Client | None = None,
        models_config: Path | None = None,
    ) -> None:
        """Load profile + endpoint; optional mock HTTP client for tests."""
        if models_config is not None:
            self._profile, self._endpoint, self._requires_api_key = (
                _load_from_path(profile_name, models_config)
            )
        else:
            self._profile = load_profile(profile_name)
            self._endpoint = resolve_endpoint(profile_name)
            self._requires_api_key = api_key_required(
                load_provider(self._endpoint.provider)
            )

        if http_client is not None and not self._endpoint.api_key:
            self._endpoint = self._endpoint.model_copy(update={"api_key": "mock-test-key"})

        self._http = http_client or httpx.Client()
        self._owns_client = http_client is None

    @property
    def profile(self) -> ModelProfile:
        """Loaded model profile."""
        return self._profile

    @property
    def endpoint(self) -> EndpointConfig:
        """Resolved provider connection."""
        return self._endpoint

    def close(self) -> None:
        """Close owned HTTP client."""
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> SLMClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        """Run chat completion; returns SLMResponse (never raises on API failure)."""
        if self._requires_api_key and not self._endpoint.api_key:
            return SLMResponse(error="missing_api_key", model=self._profile.model_id)

        timeout_s = self._profile.timeout_by_role.get(role)
        if timeout_s is None:
            return SLMResponse(
                error=f"unknown_role:{role}",
                model=self._profile.model_id,
            )

        outbound_messages = messages
        if json_mode and self._profile.tool_call_format == "json":
            outbound_messages = _ensure_json_keyword_in_messages(messages)

        payload: dict[str, Any] = {
            "model": self._profile.model_id,
            "messages": outbound_messages,
        }
        if json_mode and self._profile.tool_call_format == "json":
            payload["response_format"] = {"type": "json_object"}
        if self._profile.api_thinking:
            payload["thinking"] = {"type": "enabled"}
            if self._profile.reasoning_effort:
                payload["reasoning_effort"] = self._profile.reasoning_effort

        logger.debug(
            "[API REQUEST] role=%s model=%s messages=%d json_mode=%s prompt_chars=%d",
            role,
            self._profile.model_id,
            len(outbound_messages),
            json_mode,
            sum(len(m.get("content", "")) for m in outbound_messages),
        )

        started = time.perf_counter()
        try:
            data, status = self._call_with_retry(payload, timeout_s)
        except httpx.TimeoutException:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.debug(
                "[API RESPONSE] role=%s model=%s error=timeout elapsed_ms=%d",
                role,
                self._profile.model_id,
                elapsed_ms,
            )
            return SLMResponse(
                error="timeout",
                model=self._profile.model_id,
                elapsed_ms=elapsed_ms,
            )
        except httpx.HTTPError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("SLM HTTP error: %s", exc)
            status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
            if status >= 400:
                return SLMResponse(
                    error=f"http_{status}",
                    model=self._profile.model_id,
                    elapsed_ms=elapsed_ms,
                )
            return SLMResponse(
                error="http_error",
                model=self._profile.model_id,
                elapsed_ms=elapsed_ms,
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if status == 429:
            return SLMResponse(
                error="rate_limited",
                model=self._profile.model_id,
                elapsed_ms=elapsed_ms,
            )
        if status >= 400:
            return SLMResponse(
                error=f"http_{status}",
                model=self._profile.model_id,
                elapsed_ms=elapsed_ms,
            )

        content = ""
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            raw_content = message.get("content")
            raw_reasoning = message.get("reasoning_content")
            if isinstance(raw_content, str) and raw_content.strip():
                content = raw_content
            elif isinstance(raw_reasoning, str) and "{" in raw_reasoning:
                content = raw_reasoning
            elif isinstance(raw_reasoning, str):
                content = raw_reasoning

        usage = data.get("usage") or {}
        tokens = int(usage.get("total_tokens") or 0)
        model_used = str(data.get("model") or self._profile.model_id)

        preview = content.replace("\r", "").replace("\n", "\\n")[:400]
        logger.debug(
            "[API RESPONSE] role=%s model=%s tokens=%d elapsed_ms=%d content_len=%d preview=%s",
            role,
            model_used,
            tokens,
            elapsed_ms,
            len(content),
            preview,
        )

        return SLMResponse(
            content=content,
            model=model_used,
            tokens_used=tokens,
            elapsed_ms=elapsed_ms,
        )

    def _call_with_retry(self, payload: dict[str, Any], timeout_s: int) -> tuple[dict[str, Any], int]:
        """POST chat/completions with retries on 429/503."""
        url = f"{self._endpoint.base_url}/chat/completions"
        headers = dict(self._endpoint.headers)
        last_status = 0
        last_body: dict[str, Any] = {}

        for attempt in range(_MAX_RETRIES):
            response = self._http.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout_s,
            )
            last_status = response.status_code
            if response.status_code in (429, 503):
                last_body = response.json() if response.content else {}
                if attempt < _MAX_RETRIES - 1:
                    delay = _BACKOFF_BASE_S * (2**attempt)
                    time.sleep(delay)
                    continue
                return last_body, last_status

            response.raise_for_status()
            return response.json(), response.status_code

        return last_body, last_status


def _load_from_path(
    profile_name: str,
    config_path: Path,
) -> tuple[ModelProfile, EndpointConfig, bool]:
    """Load profile and endpoint from a test-local models.yaml."""
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profiles: dict[str, Any] = raw.get("profiles", {})
    providers: dict[str, Any] = raw.get("providers", {})
    if profile_name not in profiles:
        raise ValueError(f"Unknown model profile: {profile_name}")
    profile = ModelProfile.model_validate(profiles[profile_name])
    provider_name = (profile.provider or raw.get("active_provider", "openrouter")).strip()
    if provider_name not in providers:
        raise ValueError(f"Unknown provider: {provider_name}")
    spec = ProviderSpec.model_validate(providers[provider_name])
    key = resolve_api_key(spec)
    endpoint = EndpointConfig(
        provider=provider_name,
        base_url=resolve_base_url(spec),
        api_key=key,
        headers=build_headers(spec, key),
        model_id=profile.model_id,
    )
    return profile, endpoint, api_key_required(spec)
