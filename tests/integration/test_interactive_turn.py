"""Integration tests for interactive turn mode (V2-2)."""

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
    """Queue-based SLM stub for interactive turn tests."""

    def __init__(
        self,
        responses: list[str],
        profile: ModelProfile | None = None,
    ) -> None:
        self._responses = list(responses)
        self.profile = profile or ModelProfile(
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
        _ = messages, json_mode
        self.call_count += 1
        if not self._responses:
            return SLMResponse(error="empty_queue", model="mock")
        content = self._responses.pop(0)
        return SLMResponse(content=content, model="mock", tokens_used=1, elapsed_ms=1)

    def close(self) -> None:
        return None


def _terminate_json(message: str, turn_type: str = "answer") -> str:
    return json.dumps(
        {
            "kind": "terminate",
            "rationale": "User question answered.",
            "payload": {"user_message": message, "turn_type": turn_type},
            "references": [],
        }
    )


def _handoff_needs_plan_json() -> str:
    return json.dumps(
        {
            "kind": "handoff",
            "rationale": "Multi-file build required.",
            "payload": {"reason": "needs_plan"},
            "references": [],
        }
    )


def _planner_plan_json() -> str:
    return json.dumps(
        {
            "kind": "plan_step",
            "rationale": "Split into implementation step.",
            "payload": {
                "subtasks": [
                    {
                        "task_id": "st-build",
                        "description": "Implement the build",
                        "owner": "executor",
                    }
                ]
            },
            "references": [],
        }
    )


def _write_file_json(path: str, content: str) -> str:
    return json.dumps(
        {
            "kind": "tool_call",
            "rationale": "Create the requested file.",
            "payload": {"tool": "write_file", "file_path": path, "content": content},
            "references": [],
        }
    )


def _read_file_json(path: str) -> str:
    return json.dumps(
        {
            "kind": "tool_call",
            "rationale": "Read requested file.",
            "payload": {"tool": "read_file", "file_path": path},
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
    return MemoryStores(SQLiteBackend(tmp_path / "interactive.db"))


def _patch_slm_clients(
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


def test_chat_goal_terminates_in_one_cycle(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat goal completes in a single executor cycle with typed user_message."""
    executor = MockSLMClient([_terminate_json("The answer is 4.")])
    planner = MockSLMClient([])
    _patch_slm_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        "What is 2+2?",
        [],
        workspace,
        memory=memory,
        session_id="sess-chat",
        probe=False,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert outcome.outcome == "solved"
    assert outcome.user_message == "The answer is 4."
    assert outcome.step_count == 1
    assert executor.call_count == 1
    assert planner.call_count == 0


def test_edit_goal_writes_file_and_verifies(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edit goal applies write then terminate within the interactive loop."""
    executor = MockSLMClient(
        [
            _write_file_json("foo.txt", "hello"),
            _terminate_json("Created foo.txt.", turn_type="edit"),
        ]
    )
    planner = MockSLMClient([])
    _patch_slm_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        'create foo.txt with "hello"',
        [],
        workspace,
        memory=memory,
        session_id="sess-edit",
        probe=False,
        max_steps=6,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert (workspace / "foo.txt").read_text(encoding="utf-8") == "hello"
    assert outcome.outcome == "solved"
    assert outcome.test_passed
    assert outcome.step_count == 2
    assert executor.call_count == 2


def test_empty_file_content_goal_auto_completes(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct content read of an empty file completes without terminate."""
    (workspace / "solution.py").write_text("", encoding="utf-8")
    executor = MockSLMClient([_read_file_json("solution.py")])
    planner = MockSLMClient([])
    _patch_slm_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        "what is the content of solution.py?",
        [],
        workspace,
        memory=memory,
        session_id="sess-empty-read",
        probe=False,
        max_steps=3,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert outcome.outcome == "solved"
    assert outcome.user_message == "solution.py is empty."
    assert outcome.step_count == 0
    assert executor.call_count == 0


def test_main_file_content_completes_without_llm(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Natural-language main file reference resolves to main.py without LLM."""
    (workspace / "main.py").write_text(
        "def greet(name: str) -> str:\n    return f'hello, {name}'\n",
        encoding="utf-8",
    )
    executor = MockSLMClient([])
    planner = MockSLMClient([])
    _patch_slm_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        "what is content of main file?",
        [],
        workspace,
        memory=memory,
        session_id="sess-main-file",
        probe=False,
        max_steps=3,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert outcome.outcome == "solved"
    assert "greet" in outcome.user_message
    assert outcome.step_count == 0
    assert executor.call_count == 0


def test_list_dir_goal_completes_without_llm(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pure list-dir goals return a workspace listing without LLM cycles."""
    (workspace / "hello.txt").write_text("hi", encoding="utf-8")
    executor = MockSLMClient([])
    planner = MockSLMClient([])
    _patch_slm_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        "list files in current dir",
        [],
        workspace,
        memory=memory,
        session_id="sess-list",
        probe=False,
        max_steps=3,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert outcome.outcome == "solved"
    assert "hello.txt" in outcome.user_message
    assert outcome.step_count == 0
    assert executor.call_count == 0


def test_run_greet_goal_completes_without_llm(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run-this-code goals can execute allow-listed python without LLM."""
    (workspace / "main.py").write_text(
        "def greet(name: str) -> str:\n    return f'hello, {name}'\n",
        encoding="utf-8",
    )
    executor = MockSLMClient([])
    planner = MockSLMClient([])
    _patch_slm_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        'run this code with input "ali ebrahimi" and show me the result',
        [],
        workspace,
        memory=memory,
        session_id="sess-run-greet",
        probe=False,
        max_steps=6,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert outcome.outcome == "solved"
    assert "hello, ali ebrahimi" in outcome.user_message.lower()
    assert outcome.step_count == 0
    assert executor.call_count == 0


def test_needs_plan_promotes_to_planner(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """handoff{needs_plan} promotes to planner without an SLM-chosen transition."""
    executor = MockSLMClient(
        [
            _handoff_needs_plan_json(),
            _terminate_json("Build complete.", turn_type="build"),
        ]
    )
    planner = MockSLMClient([_planner_plan_json()])
    _patch_slm_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_turn(
        "Build a multi-file feature",
        [],
        workspace,
        memory=memory,
        session_id="sess-promote",
        probe=False,
        max_steps=8,
        checkpoint_dir=workspace.parent / "ckpt",
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    decisions = memory.decisions.list_for_session("sess-promote")
    kinds_by_agent = [(d.by_agent, d.kind) for d in decisions]
    assert ("executor", "handoff") in kinds_by_agent
    assert ("planner", "plan_step") in kinds_by_agent
    assert planner.call_count >= 1
    assert outcome.outcome == "solved"
    assert outcome.user_message == "Build complete."


def test_needs_plan_transition_is_python_not_slm(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Planner runs immediately after needs_plan handoff — no extra executor SLM first."""
    executor = MockSLMClient(
        [
            _handoff_needs_plan_json(),
            _terminate_json("Done."),
        ]
    )
    planner = MockSLMClient([_planner_plan_json()])
    _patch_slm_clients(monkeypatch, planner=planner, executor=executor)

    run_turn(
        "Large refactor across modules",
        [],
        workspace,
        memory=memory,
        session_id="sess-transition",
        probe=False,
        max_steps=8,
        checkpoint_dir=workspace.parent / "ckpt2",
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    decisions = memory.decisions.list_for_session("sess-transition")
    handoff_idx = next(i for i, d in enumerate(decisions) if d.kind == "handoff")
    planner_idx = next(i for i, d in enumerate(decisions) if d.by_agent == "planner")
    assert planner_idx > handoff_idx
    post_handoff_before_planner = decisions[handoff_idx + 1 : planner_idx]
    assert all(d.by_agent != "executor" for d in post_handoff_before_planner)


def test_run_full_session_interactive_delegates_to_run_turn(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_full_session(interactive=True) uses the interactive turn path."""
    from framework.orchestration.session import run_full_session

    executor = MockSLMClient([_terminate_json("Hi there.")])
    planner = MockSLMClient([])
    _patch_slm_clients(monkeypatch, planner=planner, executor=executor)

    outcome = run_full_session(
        "hi",
        [],
        workspace=workspace,
        memory=memory,
        session_id="sess-delegate",
        probe=False,
        interactive=True,
        ablation=AblationSettings(memory=False, control=False, error_control=False),
    )

    assert outcome.user_message == "Hi there."
    assert executor.call_count == 1
    assert planner.call_count == 0
