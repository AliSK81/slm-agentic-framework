"""Aviona project rules unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aviona.project import load_project_rules, locate_rules_file
from aviona.session import AvionaSession


def test_locate_aviona_md_preferred(tmp_path: Path) -> None:
    """AVIONA.md is preferred over .aviona/PROJECT.md."""
    (tmp_path / "AVIONA.md").write_text("alpha\n", encoding="utf-8")
    (tmp_path / ".aviona").mkdir()
    (tmp_path / ".aviona" / "PROJECT.md").write_text("beta\n", encoding="utf-8")
    assert locate_rules_file(tmp_path) == tmp_path / "AVIONA.md"


def test_load_project_rules_injects_project_rules_segment(tmp_path: Path) -> None:
    """Rules file becomes a [PROJECT RULES] hard constraint segment."""
    (tmp_path / "AVIONA.md").write_text("Always use pathlib.\n", encoding="utf-8")
    rules = load_project_rules(tmp_path)
    assert len(rules) == 1
    assert rules[0].startswith("[PROJECT RULES]")
    assert "pathlib" in rules[0]


def test_load_project_rules_missing_file_is_safe(tmp_path: Path) -> None:
    """Missing rules file returns empty constraints without error."""
    assert load_project_rules(tmp_path) == []


def test_run_turn_passes_project_rules_into_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AvionaSession merges AVIONA.md rules into interactive turn constraints."""
    (tmp_path / "AVIONA.md").write_text("No print in library code.\n", encoding="utf-8")
    session = AvionaSession(tmp_path)
    captured: list[list[str]] = []

    def fake_run(goal: str, constraints: list[str], workspace: Path, **kwargs: object) -> object:
        _ = workspace, kwargs
        captured.append(list(constraints))
        from framework.orchestration.session import SessionOutcome

        return SessionOutcome(session_id=session._session_id, outcome="solved")

    monkeypatch.setattr("aviona.session.framework_run_turn", fake_run)
    monkeypatch.setattr(
        "aviona.session.SessionStore.append_turn",
        lambda self, **kwargs: None,
    )
    session.run_turn("do something")
    assert captured
    joined = " ".join(captured[0])
    assert "[PROJECT RULES]" in joined
    assert "No print" in joined
