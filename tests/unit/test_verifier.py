"""Verifier protocol unit tests — no API."""

from __future__ import annotations

from pathlib import Path

from framework.orchestration.session import evaluate_workspace
from framework.orchestration.verify import NoOpVerifier, TestCodeVerifier


def test_test_code_verifier_matches_evaluate_workspace(tmp_path: Path) -> None:
    """TestCodeVerifier wraps evaluate_workspace for passing code."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "solution.py").write_text(
        "def multiply(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    test_code = "assert multiply(3, 4) == 12"
    direct = evaluate_workspace(workspace, test_code)
    via = TestCodeVerifier(test_code).evaluate(workspace)
    assert via.passed == direct["passed"]
    assert via.passed is True


def test_test_code_verifier_fails_on_bad_assertion(tmp_path: Path) -> None:
    """TestCodeVerifier reports failure when assertions do not hold."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "solution.py").write_text("def f():\n    return 0\n", encoding="utf-8")
    result = TestCodeVerifier("assert f() == 1").evaluate(workspace)
    assert not result.passed


def test_noop_verifier_passes_when_no_python_files(tmp_path: Path) -> None:
    """NoOpVerifier passes an empty workspace with no Python sources."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    result = NoOpVerifier().evaluate(workspace)
    assert result.passed


def test_noop_verifier_compiles_valid_python(tmp_path: Path) -> None:
    """NoOpVerifier compiles non-test *.py files in the workspace."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "mod.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    result = NoOpVerifier().evaluate(workspace)
    assert result.passed


def test_noop_verifier_fails_on_syntax_error(tmp_path: Path) -> None:
    """NoOpVerifier fails when a workspace Python file has a syntax error."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    result = NoOpVerifier().evaluate(workspace)
    assert not result.passed
    assert result.error_message
