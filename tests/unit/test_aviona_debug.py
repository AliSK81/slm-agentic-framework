"""Aviona --debug logging tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from aviona.cli import build_parser
from aviona.debug_log import (
    close_debug_log,
    debug_log_path,
    enable_debug_log,
    is_debug_enabled,
    log_event,
    log_repl_user,
)
from aviona.repl import ScriptedReader, run_repl
from aviona.session import AvionaSession, TurnResult


def test_build_parser_has_debug_flag() -> None:
    """CLI exposes --debug for file logging."""
    parser = build_parser()
    args = parser.parse_args(["--debug"])
    assert args.debug is True


def test_enable_debug_log_writes_claude_style_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Debug log uses ISO UTC timestamps and [LEVEL] prefixes."""
    monkeypatch.setattr(
        "aviona.debug_log.debug_log_dir",
        lambda: tmp_path / "debug",
    )
    path = enable_debug_log(workspace=tmp_path, session_id="aviona-test123")
    assert path.is_file()
    log_repl_user("hi")
    log_event("[API REQUEST] role=executor model=mock messages=2 json_mode=True")
    close_debug_log()
    assert not is_debug_enabled()
    assert debug_log_path() is None

    text = path.read_text(encoding="utf-8")
    assert "[DEBUG]" in text
    assert "[REPL] user input: 'hi'" in text
    assert "[API REQUEST]" in text
    assert "session_id=aviona-test123" in text
    first_line = text.splitlines()[0]
    assert first_line.startswith("202")
    assert "Z [DEBUG]" in first_line


def test_repl_debug_prints_log_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REPL startup announces debug mode and log file path."""
    monkeypatch.setattr(
        "aviona.debug_log.debug_log_dir",
        lambda: tmp_path / "debug",
    )
    session = AvionaSession(tmp_path)
    output: list[str] = []

    run_repl(
        session,
        reader=ScriptedReader(["/exit"]),
        writer=output.append,
        run_turn=lambda _text: TurnResult(status="ok", outcome="solved"),
        debug=True,
    )

    joined = "\n".join(output)
    assert "Debug mode enabled" in joined
    assert "Logging to:" in joined
    assert (tmp_path / "debug").exists()


def test_framework_trace_lines_land_in_debug_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Framework DEBUG lines propagate into the Aviona debug log file."""
    import logging

    monkeypatch.setattr(
        "aviona.debug_log.debug_log_dir",
        lambda: tmp_path / "debug",
    )
    path = enable_debug_log(workspace=tmp_path, session_id="trace-test")
    logging.getLogger("framework.control.self_check").debug(
        "[SELF_CHECK] issue kind=scope_violation detail=test detail"
    )
    logging.getLogger("framework.control.cycle").debug(
        "[CYCLE] complete agent=executor kind=terminate decision_id=d-test retries=0"
    )
    close_debug_log()

    text = path.read_text(encoding="utf-8")
    assert "[SELF_CHECK]" in text
    assert "[CYCLE]" in text
