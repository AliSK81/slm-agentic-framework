"""Aviona user journey regression tests (L2, mocked SLM)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aviona.effects import analyze_turn_effects, classify_goal, infer_target_file, is_directory_listing
from aviona.intent import is_conversational
from aviona.repl import ScriptedReader, run_repl
from aviona.session import AvionaSession
from framework.memory.stores import DecisionEntry, SelfCheckRecord
from framework.tools.file_tools import write_file

_LISTING = "hello.txt\nmain.py\n.git/\nAVIONA.md\n"


def _self_check() -> SelfCheckRecord:
    return SelfCheckRecord(verdict="pass", issues=[])


def _decision(tool: str, path: str = ".") -> DecisionEntry:
    return DecisionEntry(
        session_id="s1",
        decision_id=f"d-{tool}-{path}",
        step_index=0,
        by_agent="executor",
        kind="tool_call",
        payload={"tool": tool, "path": path},
        rationale=f"run {tool}",
        references=[],
        self_check=_self_check(),
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[1] / "fixtures" / "sample_repo"
    dest = tmp_path / "sample_repo"
    shutil.copytree(src, dest)
    write_file("hello.txt", "hi\n", dest)
    return dest


# --- J1 local chat ---


def test_j1_hi_is_conversational() -> None:
    """J1: hi is local chat, not an agent turn."""
    assert is_conversational("hi")


def test_j1_repl_skips_agent(sample_repo: Path) -> None:
    """J1: REPL does not call run_turn for hi."""
    session = AvionaSession(sample_repo)
    calls: list[str] = []

    def _track(text: str):
        calls.append(text)
        raise AssertionError("should not run turn")

    run_repl(
        session,
        reader=ScriptedReader(["hi", "/exit"]),
        writer=lambda _m: None,
        run_turn=_track,
    )
    assert calls == []


def test_j9_ok_skips_agent(sample_repo: Path) -> None:
    """J9: ok is local chat — must not invoke agent or edit files."""
    session = AvionaSession(sample_repo)
    calls: list[str] = []

    def _track(text: str):
        calls.append(text)
        raise AssertionError("should not run turn")

    lines: list[str] = []
    run_repl(
        session,
        reader=ScriptedReader(["ok", "/exit"]),
        writer=lines.append,
        run_turn=_track,
    )
    assert calls == []
    assert any("Got it" in line for line in lines)


# --- J3 read content (reported bug) ---


def test_j3_classifies_read_content() -> None:
    """J3: content question is read_content, not explain."""
    assert classify_goal("what is content of hello file?") == "read_content"


def test_j3_list_only_fails_verification() -> None:
    """J3: directory listing alone must not satisfy read_content."""
    effects = analyze_turn_effects(
        goal="what is content of hello file?",
        new_entries=[_decision("list_dir")],
        file_changes=[],
        tool_outputs=[_LISTING],
    )
    assert not effects.satisfied
    assert effects.failure_reason == "file content required"


def test_j3_read_hello_passes_verification() -> None:
    """J3: read_file body satisfies read_content."""
    effects = analyze_turn_effects(
        goal="what is content of hello file?",
        new_entries=[_decision("read_file", "hello.txt")],
        file_changes=[],
        tool_outputs=["hi\n"],
    )
    assert effects.satisfied
    assert "hi" in (effects.user_detail or "")


def test_j3_infer_target_file(sample_repo: Path) -> None:
    """J3: infer hello file from natural language."""
    assert infer_target_file("what is content of hello file?", sample_repo) == "hello.txt"


# --- J5 explain ---


def test_j5_explain_classifies() -> None:
    """J5: explain the codebase is explain goal."""
    assert classify_goal("explain the codebase") == "explain"


def test_j8_what_is_this_project_classifies_explain() -> None:
    """J8: what is this project is explain, not vacuous general."""
    assert classify_goal("what is this project") == "explain"


def test_j8_vacuous_terminate_fails_explain() -> None:
    """J8: meta terminate without repo answer must fail explain verification."""
    effects = analyze_turn_effects(
        goal="what is this project",
        new_entries=[
            DecisionEntry(
                session_id="s1",
                decision_id="d-term",
                step_index=0,
                by_agent="executor",
                kind="terminate",
                payload={},
                rationale="User asked a question about the project without a file task; no further action needed.",
                references=[],
                self_check=_self_check(),
                timestamp=datetime.now(UTC),
            )
        ],
        file_changes=[],
        tool_outputs=[],
    )
    assert not effects.satisfied


def test_j8_explain_fallback_reads_readme(sample_repo: Path) -> None:
    """J8: fallback builds summary from README when agent fails."""
    from aviona.fallbacks import try_explain_fallback

    (sample_repo / "README.md").write_text(
        "# Demo Project\n\nA sample calculator project for Aviona tests.\n",
        encoding="utf-8",
    )
    effects = try_explain_fallback(sample_repo)
    assert effects is not None
    assert effects.satisfied
    assert "Demo Project" in (effects.user_detail or "")


def test_j3_read_content_fallback(sample_repo: Path) -> None:
    """J3: fallback reads hello.txt when agent only listed directory."""
    from aviona.fallbacks import try_read_content_fallback

    effects = try_read_content_fallback("what is content of hello file?", sample_repo)
    assert effects is not None
    assert effects.satisfied
    assert "hi" in (effects.user_detail or "")


# --- J2 list ---


def test_j2_list_classifies_as_read() -> None:
    """J2: list files is read (directory), not read_content."""
    assert classify_goal("list files in this dir") == "read"


def test_j2_listing_output_passes() -> None:
    """J2: list_dir output satisfies read goal."""
    effects = analyze_turn_effects(
        goal="list files in this dir",
        new_entries=[_decision("list_dir")],
        file_changes=[],
        tool_outputs=[_LISTING],
    )
    assert effects.satisfied
    assert is_directory_listing(_LISTING)


# --- J4 read hello.txt ---


def test_j4_read_hello_txt_classifies() -> None:
    """J4: explicit read path is read_content."""
    assert classify_goal("read hello.txt") == "read_content"


# --- J6 write ---


def test_j6_create_classifies_write() -> None:
    """J6: create is write goal."""
    assert classify_goal('create foo.txt with "x"') == "write"


def test_j6_write_without_changes_fails() -> None:
    """J6: write with no edits fails verification."""
    effects = analyze_turn_effects(
        goal='create foo.txt with "x"',
        new_entries=[],
        file_changes=[],
        tool_outputs=[],
    )
    assert not effects.satisfied


# --- J7 general chat must not accept edits ---


def test_j7_general_rejects_unsolicited_edits() -> None:
    """J7: general goal with file changes fails."""
    effects = analyze_turn_effects(
        goal="thanks for the help",
        new_entries=[],
        file_changes=["hello.txt"],
        tool_outputs=[],
    )
    assert not effects.satisfied
