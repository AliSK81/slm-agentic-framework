"""Unified SLM client for OpenRouter.

All agents use this module; no direct HTTP calls elsewhere.

Purpose: load model profiles, call chat completions with retries/timeouts,
return typed SLMResponse (never raise on API failure).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MODELS_CONFIG = _PROJECT_ROOT / "configs" / "models.yaml"
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_MAX_RETRIES = 3
_BACKOFF_BASE_S = 0.5


class ModelProfile(BaseModel):
    """Model capabilities and limits from configs/models.yaml."""

    openrouter_id: str
    context_limit: int
    effective_context: int
    thinking_budget: int | None = None
    max_working_memory_tokens: int
    tool_output_caps: dict[str, int]
    skill_budget_tokens: int
    timeout_by_role: dict[str, int]
    tool_call_format: Literal["json"] = "json"


class SLMResponse(BaseModel):
    """Result of a single SLM completion call."""

    content: str = ""
    model: str = ""
    tokens_used: int = 0
    elapsed_ms: int = 0
    error: str | None = None


class SLMClient:
    """OpenRouter chat client bound to one model profile."""

    def __init__(
        self,
        profile_name: str,
        *,
        http_client: httpx.Client | None = None,
        models_config: Path | None = None,
    ) -> None:
        """Load profile and prepare HTTP client.

        Inputs:
            profile_name: key under ``profiles`` in models.yaml.
            http_client: optional client (for tests with MockTransport).
            models_config: override path to models.yaml.

        Side effects: reads env and YAML; creates httpx client if not provided.
        """
        self._api_key = os.getenv("OPENROUTER_API_KEY", "")
        self._base_url = os.getenv("OPENROUTER_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
        self._profile = self._load_profile(profile_name, models_config or _MODELS_CONFIG)
        self._http = http_client or httpx.Client()
        self._owns_client = http_client is None

    @property
    def profile(self) -> ModelProfile:
        """Loaded model profile."""
        return self._profile

    def close(self) -> None:
        """Close owned HTTP client."""
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> SLMClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @staticmethod
    def _load_profile(profile_name: str, config_path: Path) -> ModelProfile:
        """Parse a named profile from models.yaml."""
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        profiles: dict[str, Any] = raw.get("profiles", {})
        if profile_name not in profiles:
            raise ValueError(f"Unknown model profile: {profile_name}")
        return ModelProfile.model_validate(profiles[profile_name])

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        """Run chat completion for the configured model.

        Inputs:
            messages: OpenAI-style message list.
            role: planner | executor | tool_call — selects timeout.
            json_mode: request JSON object response format when True.

        Outputs:
            SLMResponse; ``error`` set on failure (never raises).
        """
        if not self._api_key:
            return SLMResponse(error="missing_api_key", model=self._profile.openrouter_id)

        timeout_s = self._profile.timeout_by_role.get(role)
        if timeout_s is None:
            return SLMResponse(
                error=f"unknown_role:{role}",
                model=self._profile.openrouter_id,
            )

        payload: dict[str, Any] = {
            "model": self._profile.openrouter_id,
            "messages": messages,
        }
        if json_mode and self._profile.tool_call_format == "json":
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            data, status = self._call_with_retry(payload, timeout_s)
        except httpx.TimeoutException:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return SLMResponse(
                error="timeout",
                model=self._profile.openrouter_id,
                elapsed_ms=elapsed_ms,
            )
        except httpx.HTTPError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("SLM HTTP error: %s", exc)
            return SLMResponse(
                error="http_error",
                model=self._profile.openrouter_id,
                elapsed_ms=elapsed_ms,
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if status == 429:
            return SLMResponse(
                error="rate_limited",
                model=self._profile.openrouter_id,
                elapsed_ms=elapsed_ms,
            )
        if status >= 400:
            return SLMResponse(
                error=f"http_{status}",
                model=self._profile.openrouter_id,
                elapsed_ms=elapsed_ms,
            )

        content = ""
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content") or ""

        usage = data.get("usage") or {}
        tokens = int(usage.get("total_tokens") or 0)
        model_used = str(data.get("model") or self._profile.openrouter_id)

        return SLMResponse(
            content=content,
            model=model_used,
            tokens_used=tokens,
            elapsed_ms=elapsed_ms,
        )

    def _call_with_retry(self, payload: dict[str, Any], timeout_s: int) -> tuple[dict[str, Any], int]:
        """POST chat/completions with retries on 429/503.

        Returns:
            Parsed JSON body and HTTP status on success.

        Raises:
            httpx.TimeoutException, httpx.HTTPError on transport failure.
        """
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "thesis-framework",
            "X-Title": "SLM-Thesis",
            "Content-Type": "application/json",
        }
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
