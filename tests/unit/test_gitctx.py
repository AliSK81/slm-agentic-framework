"""Aviona read-only git context unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aviona.gitctx import (
    _parse_porcelain,
    format_git_summary,
    git_status,
)
from framework.error_control.sandbox import SubprocessResult


def test_parse_porcelain_counts_changed_files() -> None:
    """Porcelain lines map to changed file paths."""
    text = " M src/a.py\n?? new.txt\n M src/b.py\n"
    files = _parse_porcelain(text)
    assert len(files) == 3
    assert "src/a.py" in files
    assert "new.txt" in files


def test_non_git_directory_returns_empty(tmp_path: Path) -> None:
    """Non-git cwd returns empty status without error."""
    workspace = tmp_path / "not-git"
    workspace.mkdir()
    status = git_status(workspace)
    assert status.branch == ""
    assert status.changed_files == []


def test_git_status_uses_sandbox_allowlisted_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only sandbox git commands are invoked."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    calls: list[str] = []

    def fake_safe_execute(cmd: str, cwd: Path, timeout_s: int = 30) -> SubprocessResult:
        _ = cwd, timeout_s
        calls.append(cmd)
        if "branch" in cmd:
            return SubprocessResult(ok=True, stdout="feature-x\n", exit_code=0)
        return SubprocessResult(
            ok=True,
            stdout=" M README.md\n?? notes.txt\n",
            exit_code=0,
        )

    monkeypatch.setattr("aviona.gitctx.safe_execute", fake_safe_execute)
    status = git_status(workspace)
    assert calls == ["git branch --show-current", "git status --porcelain"]
    assert status.branch == "feature-x"
    assert len(status.changed_files) == 2


def test_git_status_returns_empty_when_sandbox_blocks_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blocked git commands yield empty/partial status without raising."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    monkeypatch.setattr(
        "aviona.gitctx.safe_execute",
        lambda *args, **kwargs: SubprocessResult(
            ok=False,
            blocked=True,
            message="Command not in allow-list: git",
        ),
    )
    status = git_status(workspace)
    assert status.branch == ""
    assert status.changed_files == []


def test_format_git_summary_one_line() -> None:
    """Summary is a single short line for the REPL."""
    from aviona.gitctx import GitStatus

    line = format_git_summary(GitStatus(branch="main", changed_files=["a.py", "b.py"]))
    assert line is not None
    assert "main" in line
    assert "2 changed" in line
    assert "\n" not in line
