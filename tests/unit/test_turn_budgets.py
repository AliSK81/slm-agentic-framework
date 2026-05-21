"""Unit tests for per-turn-type budgets and read-only enforcement (V2-5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.control.ablation import AblationSettings
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import MemoryStores
from framework.orchestration.session import ProbeResult, run_turn
from framework.slm.client import ModelProfile, SLMResponse


class MockSLMClient:
    """Queue-based SLM stub counting calls."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.profile = ModelProfile(
            model_id="mock",
            context_limit=4096,
            effective_context=4096,
            max_working_memory_tokens=650,
            tool_output_caps={},
            skill_budget_tokens=120,
            timeout_by_role={"planner": 60, "executor": 75},
        )
        self.call_count = 0

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        _ = messages, role, json_mode
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


def _terminate(message: str, turn_type: str = "answer") -> str:
    return json.dumps(
        {
            "kind": "terminate",
            "rationale": "done",
            "payload": {"user_message": message, "turn_type": turn_type},
            "references": [],
        }
    )


def _tool_call(tool: str, **payload: object) -> str:
    return json.dumps(
        {
            "kind": "tool_call",
            "rationale": f"run {tool}",
            "payload": {"tool": tool, **payload},
            "references": [],
        }
    )


def _code_edit(path: str, content: str, *, turn_type: str | None = None) -> str:
    payload: dict[str, object] = {
        "file_path": path,
        "content": content,
    }
    if turn_type is not None:
        payload["turn_type"] = turn_type
    return json.dumps(
        {
            "kind": "code_edit",
            "rationale": "write file",
            "payload": payload,
            "references": [],
        }
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "budget.db"))


def _patch_clients(
    monkeypatch: pytest.MonkeyPatch,
    *,
    planner: MockSLMClient,
    executor: MockSLMClient,
) -> None:
    def fake_client_for_role(role: str) -> MockSLMClient:
        if role == "planner":
            return planner
        return executor

    monkeypatch.setattr(
        "framework.orchestration.session.client_for_role",
        fake_client_for_role,
    )
    monkeypatch.setattr(
        "framework.orchestration.session.validate_slm_api_key",
        lambda *args, **kwargs: ProbeResult(ok=True, attempts=1),
    )


def test_answer_turn_makes_exactly_one_slm_call(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Answer turn completes in a single executor LLM cycle."""
    executor = MockSLMClient([_terminate("The answer is 4.", "answer")])
    planner = MockSLMClient([])
    _patch_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        "What is 2+2?",
        [],
        workspace,
        memory=memory,
        session_id="sess-answer-budget",
        probe=False,
        max_steps=1,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert outcome.llm_calls == 1
    assert executor.call_count == 1
    assert outcome.user_message == "The answer is 4."


def test_inspect_turn_stays_within_three_cycles(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspect turn allows up to three executor cycles before terminate."""
    executor = MockSLMClient(
        [
            _tool_call("list_dir", path="."),
            _tool_call("read_file", file_path="README.md"),
            _terminate("Project overview from README.", "inspect"),
        ]
    )
    planner = MockSLMClient([])
    _patch_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        "what is this project",
        [],
        workspace,
        memory=memory,
        session_id="sess-inspect-budget",
        probe=False,
        max_steps=3,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert outcome.llm_calls == 3
    assert outcome.step_count == 3
    assert outcome.user_message == "Project overview from README."


def test_read_only_turn_blocks_write_without_edit_turn_type(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read-only interactive mode blocks code_edit when turn_type is not edit/build."""
    executor = MockSLMClient([_code_edit("notes.txt", "oops")])
    planner = MockSLMClient([])
    _patch_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        "ok",
        [],
        workspace,
        memory=memory,
        session_id="sess-readonly",
        probe=False,
        max_steps=1,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert not (workspace / "notes.txt").exists()
    assert outcome.step_count == 0
    assert outcome.llm_calls <= 4


def test_edit_turn_allows_write_with_turn_type_edit(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edit turn_type on code_edit permits the write under read-only mode."""
    executor = MockSLMClient(
        [
            _code_edit("foo.txt", "hello", turn_type="edit"),
            _terminate("Created foo.txt.", "edit"),
        ]
    )
    planner = MockSLMClient([])
    _patch_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        'create foo.txt with "hello"',
        [],
        workspace,
        memory=memory,
        session_id="sess-edit-budget",
        probe=False,
        max_steps=6,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert (workspace / "foo.txt").read_text(encoding="utf-8").strip() == "hello"
    assert outcome.user_message == "Created foo.txt."
    assert outcome.llm_calls == 2
