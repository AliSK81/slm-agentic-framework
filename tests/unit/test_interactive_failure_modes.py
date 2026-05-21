"""FI-7: mock SLM queues reproducing PROBLEM_INVENTORY interactive failure modes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from framework.control.ablation import AblationSettings
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import MemoryStores
from framework.orchestration.session import (
    ProbeResult,
    _build_agents,
    _run_interactive_executor_turn,
    run_turn,
)
from framework.orchestration.verify import NoOpVerifier
from tests.unit._mock_slm_queue import (
    QueuedSLMClient,
    code_edit,
    handoff,
    list_dir,
    pytest_run,
    read_file,
    terminate,
    write_file,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "failure_modes.db"))


def _patch_run_turn_slm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    planner: QueuedSLMClient,
    executor: QueuedSLMClient,
) -> None:
    """Wire QueuedSLMClient instances into run_turn."""

    def fake_client_for_role(role: str) -> QueuedSLMClient:
        return planner if role == "planner" else executor

    monkeypatch.setattr(
        "framework.orchestration.session.client_for_role",
        fake_client_for_role,
    )
    monkeypatch.setattr(
        "framework.orchestration.session.validate_slm_api_key",
        lambda *args, **kwargs: ProbeResult(ok=True, attempts=1),
    )


def _run_executor_turn(
    tmp_path: Path,
    workspace: Path,
    memory: MemoryStores,
    slm: QueuedSLMClient,
    *,
    goal: str = "test goal",
    interactive_read_only: bool = True,
    max_retries: int = 3,
) -> object:
    """Run one interactive executor turn with a injected SLM queue."""
    session_id = "sess-fm"
    _, executor, _, _ = _build_agents(
        memory,
        workspace,
        AblationSettings(memory=True, control=True, error_control=True),
        interactive_read_only=interactive_read_only,
    )
    executor._cycle._slm = slm  # noqa: SLF001
    return _run_interactive_executor_turn(
        goal=goal,
        constraints=[],
        workspace=workspace,
        memory=memory,
        executor=executor,
        verifier=NoOpVerifier(),
        session_id=session_id,
        max_retries=max_retries,
    )


def test_no_synthesis_from_list_dir_for_explore_goal(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R10: explore goal must not surface list_dir output as user_message."""
    executor = QueuedSLMClient([list_dir(), list_dir(), list_dir()])
    _patch_run_turn_slm(monkeypatch, planner=QueuedSLMClient([]), executor=executor)

    outcome = run_turn(
        "explore md files",
        [],
        workspace,
        memory=memory,
        session_id="sess-r10",
        probe=False,
        max_steps=3,
        interactive_read_only=True,
        ablation=AblationSettings(memory=True, control=True, error_control=True),
    )

    assert outcome.outcome == "unresolvable"
    assert "README.md" not in (outcome.user_message or "")
    assert executor.call_count >= 3


def test_read_then_terminate(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R06/R07/R08: read_file then terminate yields typed user_message (no scrape)."""
    (workspace / "notes.txt").write_text("alpha-beta-gamma", encoding="utf-8")
    executor = QueuedSLMClient(
        [
            read_file("notes.txt", turn_type="inspect"),
            terminate("alpha-beta-gamma", turn_type="inspect"),
        ]
    )
    _patch_run_turn_slm(monkeypatch, planner=QueuedSLMClient([]), executor=executor)

    outcome = run_turn(
        "what is in notes.txt?",
        [],
        workspace,
        memory=memory,
        session_id="sess-read-term",
        probe=False,
        interactive_read_only=True,
        ablation=AblationSettings(memory=True, control=True, error_control=True),
    )

    assert outcome.outcome == "solved"
    assert outcome.user_message == "alpha-beta-gamma"
    assert executor.call_count == 2


def test_read_without_terminate_honest_unresolvable_when_finalizer_off(
    tmp_path: Path,
    workspace: Path,
    memory: MemoryStores,
) -> None:
    """R07/R08: tool without terminate and finalizer:off → unresolvable, not list_dir scrape."""
    (workspace / "data.txt").write_text("payload", encoding="utf-8")
    slm = QueuedSLMClient([read_file("data.txt", turn_type="inspect")])

    with patch(
        "framework.orchestration.session.load_interactive_finalizer_enabled",
        return_value=False,
    ):
        outcome = _run_executor_turn(
            tmp_path,
            workspace,
            memory,
            slm,
            goal="read data.txt",
        )

    assert outcome.outcome == "unresolvable"
    assert not (outcome.user_message or "").strip()
    assert slm.call_count >= 1
    tool_entries = memory.tool_results.list_for_turn("sess-fm", 0)
    assert len([e for e in tool_entries if e.tool == "read_file"]) == 1


def test_partial_read_honest_limit(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R11: terminate must not invent content beyond what was read (honest partial)."""
    lines = [f"line {i}" for i in range(1, 201)]
    lines.append("UNIQUE_END_MARKER")
    (workspace / "big.txt").write_text("\n".join(lines), encoding="utf-8")
    executor = QueuedSLMClient(
        [
            read_file("big.txt", turn_type="inspect"),
            terminate(
                "The file starts with line 1; output was truncated in the tool view.",
                turn_type="inspect",
            ),
        ]
    )
    _patch_run_turn_slm(monkeypatch, planner=QueuedSLMClient([]), executor=executor)

    outcome = run_turn(
        "show me big.txt",
        [],
        workspace,
        memory=memory,
        session_id="sess-partial",
        probe=False,
        interactive_read_only=True,
        ablation=AblationSettings(memory=True, control=True, error_control=True),
    )

    assert outcome.outcome == "solved"
    assert "UNIQUE_END_MARKER" not in (outcome.user_message or "")
    assert "truncated" in (outcome.user_message or "").lower()


def test_edit_then_verify_then_terminate(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R12: edit phase write, run phase pytest, then terminate (no mid-turn scrape)."""
    executor = QueuedSLMClient(
        [
            code_edit("sample_test.py", "def test_ok():\n    assert True\n"),
            handoff("needs_run"),
            pytest_run("."),
            terminate("Created sample_test.py and ran pytest.", turn_type="edit"),
        ]
    )
    _patch_run_turn_slm(monkeypatch, planner=QueuedSLMClient([]), executor=executor)

    outcome = run_turn(
        "write a test and run pytest",
        [],
        workspace,
        memory=memory,
        session_id="sess-edit-verify",
        probe=False,
        ablation=AblationSettings(memory=True, control=True, error_control=True),
    )

    assert outcome.outcome == "solved"
    assert (workspace / "sample_test.py").is_file()
    assert "pytest" in (outcome.user_message or "").lower()


def test_compound_test_run_show(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R15: write test → run → show message uses per-phase budgets, not goal regex."""
    executor = QueuedSLMClient(
        [
            write_file("demo_test.py", "def test_demo():\n    assert 1 == 1\n"),
            handoff("needs_run"),
            pytest_run("."),
            terminate("Tests passed:\n```\n1 passed\n```", turn_type="edit"),
        ]
    )
    _patch_run_turn_slm(monkeypatch, planner=QueuedSLMClient([]), executor=executor)

    outcome = run_turn(
        "hello",  # no keyword routing
        [],
        workspace,
        memory=memory,
        session_id="sess-compound-show",
        probe=False,
        ablation=AblationSettings(memory=True, control=True, error_control=True),
    )

    assert outcome.outcome == "solved"
    assert (workspace / "demo_test.py").is_file()
    assert "passed" in (outcome.user_message or "").lower()
    decisions = memory.decisions.list_for_session("sess-compound-show")
    assert any(d.kind == "handoff" for d in decisions)


def test_anaphora_uses_recent_turn_context(
    tmp_path: Path,
    workspace: Path,
    memory: MemoryStores,
) -> None:
    """R13: terminate cycle WM includes [RECENT TURNS] after code_edit in the same turn."""
    (workspace / "target.py").write_text("old", encoding="utf-8")

    class _CapturingSLM(QueuedSLMClient):
        """Assert WM on the terminate proposal cycle."""

        def call(
            self,
            messages: list[dict[str, str]],
            role: str,
            json_mode: bool = True,
        ) -> object:
            if self.call_count == 1:
                joined = "\n".join(m.get("content", "") for m in messages)
                assert "[RECENT TURNS]" in joined
                assert "edited: target.py" in joined
            return super().call(messages, role, json_mode)

    slm = _CapturingSLM(
        [
            code_edit("target.py", "new_body\n", turn_type="edit"),
            terminate("Updated target.py.", turn_type="edit"),
        ]
    )
    outcome = _run_executor_turn(
        tmp_path,
        workspace,
        memory,
        slm,
        goal="update target.py",
        interactive_read_only=False,
    )

    assert outcome.outcome == "solved"
    assert outcome.user_message == "Updated target.py."
    assert slm.call_count == 2
