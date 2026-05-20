"""Aviona turn effect detection unit tests."""

from __future__ import annotations

from aviona.effects import (
    analyze_turn_effects,
    classify_goal,
    infer_target_file,
    is_directory_listing,
)


def test_classify_write_and_read_goals() -> None:
    """Action verbs map to write/read goal kinds."""
    assert classify_goal("create calculator.py") == "write"
    assert classify_goal("list files in current dir") == "read"
    assert classify_goal("what is content of hello file?") == "read_content"
    assert classify_goal("read hello.txt") == "read_content"


def test_write_goal_fails_without_file_changes() -> None:
    """Write goals are unsatisfied when nothing changed."""
    effects = analyze_turn_effects(
        goal="create calculator.py",
        new_entries=[],
        file_changes=[],
        tool_outputs=[],
    )
    assert not effects.satisfied
    assert effects.failure_reason == "no file changes"


def test_write_goal_passes_with_file_changes() -> None:
    """Write goals succeed when workspace files changed."""
    effects = analyze_turn_effects(
        goal="create calculator.py",
        new_entries=[],
        file_changes=["calculator.py"],
        tool_outputs=[],
    )
    assert effects.satisfied
    assert "calculator.py" in effects.edited_paths


def test_read_goal_passes_with_listing_output() -> None:
    """Read/list goals succeed when list_dir output is present."""
    listing = "AVIONA.md\nmain.py\n.git/\n"
    effects = analyze_turn_effects(
        goal="list files in current dir",
        new_entries=[],
        file_changes=[],
        tool_outputs=[listing],
    )
    assert effects.satisfied
    assert is_directory_listing(listing)


def test_read_content_rejects_listing_only() -> None:
    """Read content goals reject directory listings."""
    listing = "hello.txt\nmain.py\n.git/\n"
    effects = analyze_turn_effects(
        goal="what is content of hello file?",
        new_entries=[],
        file_changes=[],
        tool_outputs=[listing],
    )
    assert not effects.satisfied


def test_infer_target_file_stem(tmp_path) -> None:
    """infer_target_file resolves hello file to hello.txt."""
    workspace = tmp_path / "proj"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("hi\n", encoding="utf-8")
    assert infer_target_file("what is content of hello file?", workspace) == "hello.txt"
