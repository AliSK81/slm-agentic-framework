"""Tool-output truncation cap unit tests."""

from __future__ import annotations

from pathlib import Path

from framework.error_control.truncation import (
    CAPS,
    get_caps,
    set_caps_profile,
    truncate,
)
from framework.tools.file_tools import read_file
from framework.tools.test_runner import run_tests


def test_interactive_profile_lowers_pytest_and_read_file_caps() -> None:
    """Interactive Aviona profile uses smaller caps than default."""
    default = get_caps("default")
    interactive = get_caps("interactive")
    assert interactive["pytest_run"] < default["pytest_run"]
    assert interactive["read_file"] < default["read_file"]


def test_truncate_preserves_head_and_tail_for_pytest_run() -> None:
    """Oversized pytest output is capped with head and tail preserved."""
    set_caps_profile("default")
    cap = CAPS["pytest_run"]
    text = ("H" * (cap // 2)) + "MIDDLE_MARKER" + ("T" * (cap // 2))
    result = truncate(text, "pytest_run")
    assert len(result) <= cap
    assert result.startswith("H")
    assert result.endswith("T")


def test_run_tests_output_respects_configured_cap(tmp_path: Path) -> None:
    """pytest_run sandbox output is truncated to the configured cap."""
    set_caps_profile("default")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_verbose.py").write_text(
        "def test_print():\n    print('x' * 20000)\n",
        encoding="utf-8",
    )
    result = run_tests("tests/test_verbose.py", tmp_path)
    assert len(result.stdout) <= CAPS["pytest_run"]


def test_read_file_respects_configured_cap(tmp_path: Path) -> None:
    """read_file applies the read_file cap before returning content."""
    set_caps_profile("default")
    cap = CAPS["read_file"]
    (tmp_path / "big.txt").write_text("A" * (cap + 5000), encoding="utf-8")
    result = read_file("big.txt", tmp_path)
    assert result.ok
    assert result.content is not None
    assert len(result.content) <= cap
