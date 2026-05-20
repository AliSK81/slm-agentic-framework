"""SLM client unit tests — httpx MockTransport, no real API calls."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from framework.slm.client import SLMClient, SLMResponse


def _success_handler(request: httpx.Request) -> httpx.Response:
    """Return a minimal OpenRouter-style completion."""
    return httpx.Response(
        200,
        json={
            "model": "qwen/qwen-2.5-coder-7b-instruct",
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"total_tokens": 42},
        },
    )


def _make_client(
    handler: httpx.MockTransport | None = None,
    profile_name: str = "qwen2.5-coder-7b-instruct",
) -> SLMClient:
    transport = handler or httpx.MockTransport(_success_handler)
    return SLMClient(
        profile_name,
        http_client=httpx.Client(transport=transport),
    )


def test_client_loads_profile() -> None:
    """Client reads model profile from configs/models.yaml correctly."""
    client = _make_client()
    profile = client.profile
    assert profile.model_id == "qwen/qwen2.5-coder-7b-instruct"
    assert profile.timeout_by_role["planner"] == 60
    assert profile.tool_call_format == "json"
    client.close()


def test_client_returns_slm_response_on_success() -> None:
    """Mocked 200 response → SLMResponse with content, no error."""
    client = _make_client()
    result = client.call([{"role": "user", "content": "hi"}], role="planner")
    assert isinstance(result, SLMResponse)
    assert result.error is None
    assert result.content == '{"ok": true}'
    assert result.tokens_used == 42
    client.close()


def test_client_returns_http_402_on_payment_required() -> None:
    """402 from httpx → SLMResponse(error='http_402'), no raise."""

    def payment_required(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": "payment required"})

    client = SLMClient(
        "qwen2.5-coder-7b-instruct",
        http_client=httpx.Client(transport=httpx.MockTransport(payment_required)),
    )
    result = client.call([{"role": "user", "content": "hi"}], role="planner")
    assert result.error == "http_402"
    client.close()


def test_client_returns_error_response_on_429() -> None:
    """429 after 3 retries → SLMResponse(error='rate_limited'), no raise."""

    def always_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    client = SLMClient(
        "qwen2.5-coder-7b-instruct",
        http_client=httpx.Client(transport=httpx.MockTransport(always_429)),
    )
    result = client.call([{"role": "user", "content": "hi"}], role="planner")
    assert result.error == "rate_limited"
    client.close()


def test_client_returns_error_response_on_timeout() -> None:
    """Timeout → SLMResponse(error='timeout'), no raise."""

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    client = SLMClient(
        "qwen2.5-coder-7b-instruct",
        http_client=httpx.Client(transport=httpx.MockTransport(timeout_handler)),
    )
    result = client.call([{"role": "user", "content": "hi"}], role="planner")
    assert result.error == "timeout"
    client.close()


def test_client_json_mode_sets_response_format() -> None:
    """json_mode=True → request payload contains response_format."""
    captured: dict[str, Any] = {}

    def capture_handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return _success_handler(request)

    client = SLMClient(
        "qwen2.5-coder-7b-instruct",
        http_client=httpx.Client(transport=httpx.MockTransport(capture_handler)),
    )
    client.call([{"role": "user", "content": "hi"}], role="planner", json_mode=True)
    assert captured["body"]["response_format"] == {"type": "json_object"}
    client.close()


def test_client_injects_json_keyword_for_json_object_mode() -> None:
    """Prompts without 'json' get a suffix so DeepSeek json_object mode is accepted."""
    captured: dict[str, Any] = {}

    def capture_handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return _success_handler(request)

    client = SLMClient(
        "default",
        http_client=httpx.Client(transport=httpx.MockTransport(capture_handler)),
    )
    client.call([{"role": "user", "content": "ping"}], role="planner", json_mode=True)
    content = captured["body"]["messages"][0]["content"].lower()
    assert "json" in content
    client.close()


def test_client_deepseek_thinking_payload() -> None:
    """Profile with api_thinking sends thinking and reasoning_effort in the request."""
    captured: dict[str, Any] = {}

    def capture_handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return _success_handler(request)

    client = SLMClient(
        "default",
        http_client=httpx.Client(transport=httpx.MockTransport(capture_handler)),
    )
    client.call([{"role": "user", "content": "hi"}], role="planner", json_mode=False)
    assert captured["body"]["thinking"] == {"type": "enabled"}
    assert captured["body"]["reasoning_effort"] == "high"
    client.close()


def test_client_applies_role_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """role='planner' → uses profile.timeout_by_role['planner']."""
    seen_timeout: int | httpx.Timeout | None = None

    original_post = httpx.Client.post

    def post_with_capture(
        self: httpx.Client,
        url: str,
        *,
        timeout: int | httpx.Timeout | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        nonlocal seen_timeout
        seen_timeout = timeout
        return original_post(self, url, timeout=timeout, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", post_with_capture)
    client = _make_client()
    client.call([{"role": "user", "content": "hi"}], role="planner")
    assert seen_timeout == 60
    client.close()
