"""Bounded tool interface unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.error_control.truncation import CAPS
from framework.tools.compile_check import py_compile_check
from framework.tools.file_tools import edit_file, read_file, write_file
from framework.tools.search import build_keyword_index, search_codebase
from framework.tools.test_runner import run_tests


def test_compile_check_passes_valid_python() -> None:
    result = py_compile_check("def add(a, b):\n    return a + b\n")
    assert result.ok
    assert result.errors == []


def test_compile_check_fails_syntax_error() -> None:
    result = py_compile_check("def broken(:\n    pass\n")
    assert not result.ok
    assert result.errors


def test_compile_check_returns_line_number() -> None:
    result = py_compile_check("def broken(:\n    pass\n")
    assert any("line" in err for err in result.errors)


def test_run_tests_passes_correct_code(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_ok.py").write_text(
        "def test_add():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    result = run_tests("tests/test_ok.py", tmp_path)
    assert result.passed
    assert result.exit_code == 0


def test_run_tests_fails_wrong_code(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_bad.py").write_text(
        "def test_fail():\n    assert 1 == 2\n",
        encoding="utf-8",
    )
    result = run_tests("tests/test_bad.py", tmp_path)
    assert not result.passed


def test_run_tests_output_is_truncated(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_verbose.py").write_text(
        "def test_print():\n    print('x' * 20000)\n",
        encoding="utf-8",
    )
    result = run_tests("tests/test_verbose.py", tmp_path)
    cap = CAPS["pytest_run"]
    assert len(result.stdout) <= cap


def test_write_file_creates_new_file(tmp_path: Path) -> None:
    result = write_file("new_module.py", "x = 1\n", tmp_path)
    assert result.ok
    assert (tmp_path / "new_module.py").read_text(encoding="utf-8") == "x = 1\n"


def test_write_file_refuses_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "exists.py"
    path.write_text("original\n", encoding="utf-8")
    result = write_file("exists.py", "new\n", tmp_path)
    assert not result.ok
    assert path.read_text(encoding="utf-8") == "original\n"


def test_write_file_prescriptive_error_contains_edit_call(tmp_path: Path) -> None:
    path = tmp_path / "exists.py"
    path.write_text("original\n", encoding="utf-8")
    result = write_file("exists.py", "new\n", tmp_path)
    assert "edit_file" in result.message


def test_edit_file_replaces_exact_match(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_text("def foo():\n    return 1\n", encoding="utf-8")
    result = edit_file("module.py", "return 1", "return 2", tmp_path)
    assert result.ok
    assert "return 2" in path.read_text(encoding="utf-8")


def test_edit_file_fails_when_old_string_not_found(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_text("def foo():\n    pass\n", encoding="utf-8")
    result = edit_file("module.py", "missing", "x", tmp_path)
    assert not result.ok


def test_edit_file_fails_when_old_string_appears_twice(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_text("x = 1\nx = 1\n", encoding="utf-8")
    result = edit_file("module.py", "x = 1", "x = 2", tmp_path)
    assert not result.ok


def test_edit_file_ast_gate_rejects_syntax_error(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_text("def foo():\n    return 1\n", encoding="utf-8")
    result = edit_file("module.py", "return 1", "return (", tmp_path)
    assert not result.ok
    assert "AST gate" in result.message


def test_edit_file_ast_gate_keeps_original_on_reject(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    original = "def foo():\n    return 1\n"
    path.write_text(original, encoding="utf-8")
    edit_file("module.py", "return 1", "return (", tmp_path)
    assert path.read_text(encoding="utf-8") == original


def test_search_codebase_bigram_scores_higher(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "alpha.py").write_text(
        "def alpha_beta_gamma():\n    return 'alpha beta gamma'\n",
        encoding="utf-8",
    )
    (pkg / "other.py").write_text(
        "def unrelated():\n    return 0\n",
        encoding="utf-8",
    )
    index = build_keyword_index(tmp_path)
    bigram_hits = search_codebase("alpha beta", index, top_k=3)
    unigram_hits = search_codebase("alpha", index, top_k=3)
    assert bigram_hits
    assert bigram_hits[0].file.endswith("alpha.py")
    if unigram_hits:
        assert bigram_hits[0].file == "pkg/alpha.py" or bigram_hits[0].file.endswith(
            "alpha.py"
        )
