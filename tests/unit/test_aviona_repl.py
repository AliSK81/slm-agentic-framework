"""Aviona REPL unit tests — scripted reader, no API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aviona.repl import ScriptedReader, run_repl
from aviona.session import AvionaSession, TurnResult


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    workspace = tmp_path / "proj"
    workspace.mkdir()
    return workspace


def test_repl_runs_one_turn_then_exits_on_slash_exit(project_dir: Path) -> None:
    """Scripted input runs one turn then stops on /exit."""
    session = AvionaSession(project_dir)
    run_turn = MagicMock(
        return_value=TurnResult(
            status="✓ · 1 steps",
            outcome="solved",
            test_passed=True,
            step_count=1,
            session_id=session._session_id,
        )
    )
    lines: list[str] = []

    def writer(msg: str) -> None:
        lines.append(msg)

    code = run_repl(
        session,
        reader=ScriptedReader(["create hello.txt with hi", "/exit"]),
        writer=writer,
        run_turn=run_turn,
    )
    assert code == 0
    run_turn.assert_called_once_with("create hello.txt with hi")
    assert any("steps" in line for line in lines)


def test_repl_help_does_not_invoke_turn(project_dir: Path) -> None:
    """/help prints commands without calling run_turn."""
    session = AvionaSession(project_dir)
    run_turn = MagicMock()
    output: list[str] = []

    run_repl(
        session,
        reader=ScriptedReader(["/help", "/exit"]),
        writer=output.append,
        run_turn=run_turn,
    )
    run_turn.assert_not_called()
    joined = "\n".join(output)
    assert "/exit" in joined
    assert "/help" in joined


def test_repl_survives_keyboard_interrupt_during_turn(project_dir: Path) -> None:
    """Ctrl-C during a turn cancels that turn and the REPL continues."""
    session = AvionaSession(project_dir)
    calls = 0

    def flaky_turn(_text: str) -> TurnResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise KeyboardInterrupt
        return TurnResult(
            status="✓ · 1 steps",
            outcome="solved",
            session_id=session._session_id,
        )

    output: list[str] = []
    run_repl(
        session,
        reader=ScriptedReader(["first", "second", "/exit"]),
        writer=output.append,
        run_turn=flaky_turn,
    )
    assert calls == 2
    assert any("cancelled" in line for line in output)
    assert any("steps" in line for line in output)
