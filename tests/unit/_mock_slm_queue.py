"""Scripted SLM queue for interactive failure-mode tests (FI-7)."""

from __future__ import annotations

import json
from typing import Any

from framework.slm.client import ModelProfile, SLMResponse


def proposal(
    *,
    kind: str,
    rationale: str = "mock",
    payload: dict[str, Any] | None = None,
    references: list[str] | None = None,
) -> str:
    """Serialize one Decision Cycle proposal JSON string."""
    return json.dumps(
        {
            "kind": kind,
            "rationale": rationale,
            "payload": payload or {},
            "references": references or [],
        }
    )


def terminate(
    user_message: str,
    *,
    turn_type: str = "inspect",
    rationale: str = "done",
) -> str:
    """Typed terminate proposal."""
    return proposal(
        kind="terminate",
        rationale=rationale,
        payload={"user_message": user_message, "turn_type": turn_type},
    )


def handoff(reason: str) -> str:
    """Typed handoff for compound phase promotion."""
    return proposal(
        kind="handoff",
        rationale="phase promotion",
        payload={"reason": reason},
    )


def read_file(path: str, *, turn_type: str = "inspect") -> str:
    """read_file tool_call proposal."""
    return proposal(
        kind="tool_call",
        rationale="read",
        payload={"tool": "read_file", "file_path": path, "turn_type": turn_type},
    )


def list_dir(path: str = ".", *, turn_type: str = "inspect") -> str:
    """list_dir tool_call proposal."""
    return proposal(
        kind="tool_call",
        rationale="list",
        payload={"tool": "list_dir", "path": path, "turn_type": turn_type},
    )


def code_edit(path: str, content: str, *, turn_type: str = "edit") -> str:
    """code_edit proposal."""
    return proposal(
        kind="code_edit",
        rationale="edit",
        payload={"file_path": path, "new_string": content, "turn_type": turn_type},
    )


def write_file(path: str, content: str, *, turn_type: str = "edit") -> str:
    """write_file tool_call proposal."""
    return proposal(
        kind="tool_call",
        rationale="write",
        payload={
            "tool": "write_file",
            "file_path": path,
            "content": content,
            "turn_type": turn_type,
        },
    )


def pytest_run(target: str = ".", *, turn_type: str = "inspect") -> str:
    """pytest tool_call proposal."""
    return proposal(
        kind="tool_call",
        rationale="verify",
        payload={"tool": "pytest", "target": target, "turn_type": turn_type},
    )


class QueuedSLMClient:
    """Pop scripted JSON proposals from a queue on each call."""

    def __init__(
        self,
        responses: list[str],
        *,
        profile: ModelProfile | None = None,
    ) -> None:
        self._responses = list(responses)
        self.call_count = 0
        self.last_messages: list[dict[str, str]] = []
        self.profile = profile or ModelProfile(
            model_id="mock",
            context_limit=4096,
            effective_context=4096,
            max_working_memory_tokens=650,
            tool_output_caps={},
            skill_budget_tokens=120,
            timeout_by_role={"planner": 60, "executor": 75},
        )

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        _ = role, json_mode
        self.last_messages = list(messages)
        self.call_count += 1
        if not self._responses:
            return SLMResponse(error="empty_queue", model="mock")
        return SLMResponse(
            content=self._responses.pop(0),
            model="mock",
            tokens_used=1,
            elapsed_ms=1,
        )

    def close(self) -> None:
        return None
