"""Aviona permission mode unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from aviona.permissions import (
    PermissionAction,
    PermissionGate,
    merged_safe_commands,
)
from aviona.settings import load_settings
from framework.error_control.sandbox import SAFE_COMMANDS
from framework.orchestration.executor import ExecutorAgent
from framework.tools.file_tools import write_file


def test_plan_mode_blocks_write_file() -> None:
    """Plan mode denies file writes."""
    gate = PermissionGate("plan")
    assert gate.check(PermissionAction(kind="write_file", detail="hello.txt")) == "deny"
    assert not gate.ensure(PermissionAction(kind="write_file", detail="hello.txt"))


def test_auto_mode_allows_write_file() -> None:
    """Auto mode allows cwd writes without confirmation."""
    gate = PermissionGate("auto")
    assert gate.check(PermissionAction(kind="write_file", detail="hello.txt")) == "allow"
    assert gate.ensure(PermissionAction(kind="write_file", detail="hello.txt"))


def test_default_mode_asks_before_side_effect_shell() -> None:
    """Default mode asks before pytest/shell side effects."""
    answers: list[bool] = []

    def confirm(_prompt: str) -> bool:
        answers.append(True)
        return True

    gate = PermissionGate("default", allowlist=["pytest"], confirm=confirm)
    assert gate.check(PermissionAction(kind="shell", detail="pytest tests/")) == "ask"
    assert gate.ensure(PermissionAction(kind="shell", detail="pytest tests/"))
    assert answers


def test_default_mode_denies_shell_when_user_declines() -> None:
    """Default mode blocks shell when confirmation is rejected."""
    gate = PermissionGate("default", allowlist=["pytest"], confirm=lambda _p: False)
    assert not gate.ensure(PermissionAction(kind="shell", detail="pytest tests/"))


def test_command_not_in_project_allowlist_is_denied() -> None:
    """Shell commands outside the project allowlist are denied."""
    gate = PermissionGate("auto", allowlist=["pytest"])
    assert gate.check(PermissionAction(kind="shell", detail="python run.py")) == "deny"


def test_unsafe_shell_denied_even_when_in_project_allowlist() -> None:
    """Project allowlist cannot widen framework SAFE_COMMANDS."""
    gate = PermissionGate("auto", allowlist=["rm -rf"])
    assert gate.check(PermissionAction(kind="shell", detail="rm -rf /")) == "deny"


def test_merged_safe_commands_never_exceeds_framework() -> None:
    """merged_safe_commands is always a subset of SAFE_COMMANDS."""
    merged = merged_safe_commands(["pytest", "git", "python", "rm"])
    assert merged <= SAFE_COMMANDS
    assert "pytest" in merged
    assert "git" in merged
    assert "rm" not in merged


def test_load_settings_from_project_yaml(tmp_path: Path) -> None:
    """`.aviona/settings.yaml` supplies mode and command allowlist."""
    settings_dir = tmp_path / ".aviona"
    settings_dir.mkdir()
    (settings_dir / "settings.yaml").write_text(
        "mode: plan\ncommands:\n  - pytest\n  - cat\n",
        encoding="utf-8",
    )
    loaded = load_settings(tmp_path)
    assert loaded.mode == "plan"
    assert "pytest" in loaded.commands


def test_executor_respects_plan_mode_write_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Executor returns permission denied when plan mode blocks write_file."""
    from framework.control.cycle import DecisionCycle
    from framework.control.models import ErrorControlBundle
    from framework.memory.backend import SQLiteBackend
    from framework.memory.stores import DecisionEntry, MemoryStores, SubTask
    from framework.memory.working_memory import WorkingMemoryBuilder
    from framework.orchestration.messages import DispatchMessage, save_dispatch
    from framework.slm.client import ModelProfile, SLMResponse
    import json

    workspace = tmp_path / "proj"
    workspace.mkdir()
    memory = MemoryStores(SQLiteBackend(tmp_path / "exec.db"))
    session_id = "sess-perm"
    memory.subtasks.register(
        SubTask(
            task_id=f"root:{session_id}",
            parent_session_id=session_id,
            description="root",
            status="open",
            owner="planner",
        )
    )
    save_dispatch(
        memory.backend,
        DispatchMessage(
            session_id=session_id,
            task_id="st-write",
            subtask_description="create file",
            step_budget=3,
            hard_constraints=[],
        ),
    )

    gate = PermissionGate("plan")

    def permission_check(kind: str, detail: str) -> bool:
        return gate.ensure(PermissionAction(kind=kind, detail=detail))  # type: ignore[arg-type]

    class StubSLM:
        profile = ModelProfile(
            model_id="mock",
            context_limit=4096,
            effective_context=4096,
            max_working_memory_tokens=650,
            tool_output_caps={},
            skill_budget_tokens=120,
            timeout_by_role={"planner": 60, "executor": 75},
        )

        def call(self, messages, role, json_mode=True):
            _ = messages, role, json_mode
            return SLMResponse(
                content=json.dumps(
                    {
                        "kind": "tool_call",
                        "payload": {
                            "tool": "write_file",
                            "file_path": "hello.txt",
                            "content": "hi\n",
                        },
                        "rationale": "create hello",
                        "references": [],
                    }
                ),
                model="mock",
            )

        def close(self):
            pass

    slm = StubSLM()
    cycle = DecisionCycle(
        slm,
        memory,
        WorkingMemoryBuilder(memory, slm.profile),
        ErrorControlBundle(),
        slm.profile,
    )
    executor = ExecutorAgent(
        cycle,
        memory,
        workspace,
        permission_check=permission_check,
    )
    state = {
        "session_id": session_id,
        "active_subtask_id": "st-write",
        "retry_count": 0,
    }
    executor.execute_node(state)
    assert executor.last_edit_result is not None
    assert not executor.last_edit_result.ok
    assert "permission denied" in executor.last_edit_result.message.lower()
    assert not (workspace / "hello.txt").exists()


def test_auto_mode_allows_write_file_on_disk(tmp_path: Path) -> None:
    """Auto permission mode allows write_file at the tool layer."""
    gate = PermissionGate("auto")
    assert gate.ensure(PermissionAction(kind="write_file", detail="hello.txt"))
    workspace = tmp_path / "proj"
    workspace.mkdir()
    result = write_file("hello.txt", "hi\n", workspace)
    assert result.ok
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "hi\n"
