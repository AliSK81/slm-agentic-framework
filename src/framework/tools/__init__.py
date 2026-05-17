"""Bounded tool interface for agents."""

from framework.tools.compile_check import CompileResult, py_compile_check
from framework.tools.file_tools import FileResult, edit_file, read_file, write_file
from framework.tools.search import CodeChunk, build_keyword_index, search_codebase
from framework.tools.test_runner import TestResult, run_tests

__all__ = [
    "CodeChunk",
    "CompileResult",
    "FileResult",
    "TestResult",
    "build_keyword_index",
    "edit_file",
    "py_compile_check",
    "read_file",
    "run_tests",
    "search_codebase",
    "write_file",
]
