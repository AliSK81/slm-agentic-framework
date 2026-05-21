"""FI-4: finalizer cycle and honest user_message contract."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from framework.control.ablation import AblationSettings
from framework.control.interactive import clear_interactive_config_cache
from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord
from framework.orchestration.session import (
    _run_interactive_executor_turn,
    _session_user_message_from_decisions,
)
from framework.orchestration.verify import NoOpVerifier
from framework.slm.client import ModelProfile, SLMResponse


class _QueueSLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0
        self.profile = ModelProfile(
            model_id="mock",
            context_limit=4096,
            effective_context=4096,
            max_working_memory_tokens=650,
            tool_output_caps={},
            skill_budget_tokens=120,
            timeout_by_role={"executor": 75},
        )

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        _ = messages, role, json_mode
        self.call_count += 1
        if not self._responses:
            return SLMResponse(error="empty", model="mock")
        return SLMResponse(
            content=self._responses.pop(0),
            model="mock",
            tokens_used=1,
            elapsed_ms=1,
        )

    def close(self) -> None:
        return None


def _read_file(turn_type: str = "inspect") -> str:
    return json.dumps(
        {
            "kind": "tool_call",
            "rationale": "read",
            "payload": {
                "tool": "read_file",
                "file_path": "notes.txt",
                "turn_type": turn_type,
            },
            "references": [],
        }
    )


def _terminate(msg: str, turn_type: str = "inspect") -> str:
    return json.dumps(
        {
            "kind": "terminate",
            "rationale": "done",
            "payload": {"user_message": msg, "turn_type": turn_type},
            "references": [],
        }
    )


def test_session_user_message_only_from_terminate_decision(tmp_path: Path) -> None:
    """user_message is empty unless a terminate decision exists in the turn."""
    memory = MemoryStores.sqlite(tmp_path / "contract.db")
    session_id = "sess-contract"
    memory.decisions.append(
        DecisionEntry(
            session_id=session_id,
            decision_id="d-tool",
            step_index=0,
            by_agent="executor",
            kind="tool_call",
            payload={"tool": "list_dir", "path": "."},
            rationale="list",
            references=[],
            self_check=SelfCheckRecord(verdict="pass", issues=[]),
            timestamp=datetime.now(UTC),
        )
    )
    assert _session_user_message_from_decisions(memory, session_id) == ""

    memory.decisions.append(
        DecisionEntry(
            session_id=session_id,
            decision_id="d-term",
            step_index=1,
            by_agent="executor",
            kind="terminate",
            payload={"user_message": "Hello user.", "turn_type": "answer"},
            rationale="done",
            references=[],
            self_check=SelfCheckRecord(verdict="pass", issues=[]),
            timestamp=datetime.now(UTC),
        )
    )
    assert _session_user_message_from_decisions(memory, session_id) == "Hello user."


def test_finalizer_on_emits_terminate_from_tool_results(tmp_path: Path) -> None:
    """Tool ran without terminate; finalizer:on produces user_message via terminate."""
    from framework.orchestration.session import _build_agents

    clear_interactive_config_cache()
    memory = MemoryStores.sqlite(tmp_path / "fin.db")
    session_id = "sess-fin"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("secret-content", encoding="utf-8")

    class _ReadThenFinalizeSLM(_QueueSLM):
        """First call: read_file; second call (finalizer): terminate."""

        def call(
            self,
            messages: list[dict[str, str]],
            role: str,
            json_mode: bool = True,
        ) -> SLMResponse:
            if self.call_count == 0:
                self._responses = [_read_file()]
            else:
                self._responses = [_terminate("secret-content")]
            return super().call(messages, role, json_mode)

    slm = _ReadThenFinalizeSLM([])
    _, executor, _, _ = _build_agents(
        memory,
        workspace,
        AblationSettings(memory=True, control=True, error_control=True),
        interactive_read_only=True,
    )
    executor._cycle._slm = slm  # noqa: SLF001

    with patch(
        "framework.orchestration.session.load_interactive_finalizer_enabled",
        return_value=True,
    ):
        outcome = _run_interactive_executor_turn(
            goal="what is in notes.txt",
            constraints=[],
            workspace=workspace,
            memory=memory,
            executor=executor,
            verifier=NoOpVerifier(),
            session_id=session_id,
            max_retries=2,
        )

    assert outcome.outcome == "solved"
    assert outcome.user_message == "secret-content"
    assert slm.call_count >= 2
    terms = [e for e in memory.decisions.list_for_session(session_id) if e.kind == "terminate"]
    assert len(terms) == 1


def test_finalizer_off_immediate_unresolvable(tmp_path: Path) -> None:
    """finalizer:off → no recovery; empty user_message and unresolvable."""
    from framework.orchestration.session import _build_agents

    memory = MemoryStores.sqlite(tmp_path / "off.db")
    session_id = "sess-off"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    slm = _QueueSLM([_read_file()])
    _, executor, _, _ = _build_agents(
        memory,
        workspace,
        AblationSettings(memory=True, control=True, error_control=True),
        interactive_read_only=True,
    )
    executor._cycle._slm = slm  # noqa: SLF001

    with patch(
        "framework.orchestration.session.load_interactive_finalizer_enabled",
        return_value=False,
    ):
        outcome = _run_interactive_executor_turn(
            goal="what is in notes.txt",
            constraints=[],
            workspace=workspace,
            memory=memory,
            executor=executor,
            verifier=NoOpVerifier(),
            session_id=session_id,
            max_retries=2,
        )

    assert outcome.outcome == "unresolvable"
    assert outcome.user_message == ""
    assert slm.call_count >= 1
    assert not any(
        e.kind == "terminate"
        for e in memory.decisions.list_for_session(session_id)
    )


def test_finalizer_failure_honest_empty_message(tmp_path: Path) -> None:
    """When finalizer exhausts without terminate, user_message stays empty."""
    from framework.orchestration.session import _build_agents

    memory = MemoryStores.sqlite(tmp_path / "fail.db")
    session_id = "sess-fail"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    slm = _QueueSLM([_read_file(), json.dumps({"kind": "tool_call", "rationale": "x", "payload": {}, "references": []})])
    _, executor, _, _ = _build_agents(
        memory,
        workspace,
        AblationSettings(memory=True, control=True, error_control=True),
        interactive_read_only=True,
    )
    executor._cycle._slm = slm  # noqa: SLF001

    with patch(
        "framework.orchestration.session.load_interactive_finalizer_enabled",
        return_value=True,
    ):
        outcome = _run_interactive_executor_turn(
            goal="what is in notes.txt",
            constraints=[],
            workspace=workspace,
            memory=memory,
            executor=executor,
            verifier=NoOpVerifier(),
            session_id=session_id,
            max_retries=1,
        )

    assert outcome.outcome == "unresolvable"
    assert outcome.user_message == ""
