"""FI-5: compound turns via typed handoff phase machine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.control.ablation import AblationSettings
from framework.control.models import handoff_reason
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import MemoryStores
from framework.orchestration.session import run_turn
from framework.slm.client import ModelProfile, SLMResponse


class MockSLMClient:
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
            timeout_by_role={"planner": 60, "executor": 75},
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
            return SLMResponse(error="empty_queue", model="mock")
        return SLMResponse(
            content=self._responses.pop(0),
            model="mock",
            tokens_used=1,
            elapsed_ms=1,
        )

    def close(self) -> None:
        return None


def _terminate(msg: str, turn_type: str = "inspect") -> str:
    return json.dumps(
        {
            "kind": "terminate",
            "rationale": "done",
            "payload": {"user_message": msg, "turn_type": turn_type},
            "references": [],
        }
    )


def _handoff(reason: str) -> str:
    return json.dumps(
        {
            "kind": "handoff",
            "rationale": "phase promotion",
            "payload": {"reason": reason},
            "references": [],
        }
    )


def _read_file(path: str, turn_type: str = "inspect") -> str:
    return json.dumps(
        {
            "kind": "tool_call",
            "rationale": "read context",
            "payload": {"tool": "read_file", "file_path": path, "turn_type": turn_type},
            "references": [],
        }
    )


def _code_edit(path: str, content: str) -> str:
    return json.dumps(
        {
            "kind": "code_edit",
            "rationale": "write file",
            "payload": {
                "file_path": path,
                "new_string": content,
                "turn_type": "edit",
            },
            "references": [],
        }
    )


def _pytest_run(target: str = ".") -> str:
    return json.dumps(
        {
            "kind": "tool_call",
            "rationale": "verify",
            "payload": {"tool": "pytest", "target": target, "turn_type": "inspect"},
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
    return MemoryStores(SQLiteBackend(tmp_path / "compound.db"))


def _patch_slm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    planner: MockSLMClient,
    executor: MockSLMClient,
) -> None:
    def fake_client_for_role(role: str) -> MockSLMClient:
        return planner if role == "planner" else executor

    monkeypatch.setattr(
        "framework.orchestration.session.client_for_role",
        fake_client_for_role,
    )
    monkeypatch.setattr(
        "framework.orchestration.session.validate_slm_api_key",
        lambda *args, **kwargs: __import__(
            "framework.orchestration.session", fromlist=["ProbeResult"]
        ).ProbeResult(ok=True, attempts=1),
    )


def test_inspect_promotes_via_handoff_needs_edit_not_goal_regex(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read-only inspect promotes to edit only through typed handoff."""
    (workspace / "target.txt").write_text("old", encoding="utf-8")
    executor = MockSLMClient(
        [
            _read_file("target.txt", "inspect"),
            _handoff("needs_edit"),
            _code_edit("target.txt", "new content"),
            _terminate("Updated target.txt.", "edit"),
        ]
    )
    _patch_slm(monkeypatch, planner=MockSLMClient([]), executor=executor)

    outcome = run_turn(
        "Please update the file",  # no keyword regex for edit
        [],
        workspace,
        memory=memory,
        session_id="sess-handoff-edit",
        probe=False,
        ablation=AblationSettings(memory=True, control=True, error_control=True),
        interactive_read_only=True,
    )

    assert outcome.outcome == "solved"
    assert (workspace / "target.txt").read_text(encoding="utf-8").strip() == "new content"
    decisions = memory.decisions.list_for_session("sess-handoff-edit")
    handoffs = [d for d in decisions if d.kind == "handoff"]
    assert len(handoffs) == 1
    assert handoff_reason(handoffs[0]) == "needs_edit"


def test_write_and_run_uses_edit_then_run_phases(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edit phase writes; run phase executes pytest before terminate."""
    executor = MockSLMClient(
        [
            _code_edit("test_sample.py", "def test_x():\n    assert True\n"),
            _handoff("needs_run"),
            _pytest_run(),
            _terminate("Tests passed.", "edit"),
        ]
    )
    _patch_slm(monkeypatch, planner=MockSLMClient([]), executor=executor)

    outcome = run_turn(
        "create test_sample.py and run pytest",
        [],
        workspace,
        memory=memory,
        session_id="sess-edit-run",
        probe=False,
        ablation=AblationSettings(memory=True, control=True, error_control=True),
    )

    assert outcome.outcome == "solved"
    assert (workspace / "test_sample.py").is_file()
    decisions = memory.decisions.list_for_session("sess-edit-run")
    assert any(handoff_reason(d) == "needs_run" for d in decisions if d.kind == "handoff")
    assert any(d.kind == "tool_call" and "pytest" in str(d.payload) for d in decisions)


def test_needs_plan_promotes_without_goal_keyword_gate(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """needs_plan handoff promotes to planner without goal substring heuristics."""
    executor = MockSLMClient(
        [
            _handoff("needs_plan"),
            _terminate("Plan phase complete.", "build"),
        ]
    )
    planner = MockSLMClient(
        [
            json.dumps(
                {
                    "kind": "plan_step",
                    "rationale": "plan",
                    "payload": {"subtasks": []},
                    "references": [],
                }
            )
        ]
    )
    _patch_slm(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        "hello",  # no build keywords
        [],
        workspace,
        memory=memory,
        session_id="sess-plan",
        probe=False,
        max_steps=8,
        checkpoint_dir=workspace.parent / "ckpt",
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    decisions = memory.decisions.list_for_session("sess-plan")
    handoffs = [d for d in decisions if d.kind == "handoff"]
    assert len(handoffs) == 1
    assert handoff_reason(handoffs[0]) == "needs_plan"
    assert ("planner", "plan_step") in [(d.by_agent, d.kind) for d in decisions]
    assert planner.call_count >= 1
    assert outcome.outcome == "solved"
