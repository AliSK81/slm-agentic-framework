"""Sandboxed pytest runner with truncated output."""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path

from pydantic import BaseModel, Field

from framework.error_control.sandbox import safe_execute
from framework.error_control.truncation import truncate

logger = logging.getLogger(__name__)

_PASSED_RE = re.compile(r"(\d+)\s+passed")
_FAILED_LINE_RE = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)


class TestResult(BaseModel):
    """Typed pytest execution result."""

    passed: bool
    total_tests: int = 0
    failed_tests: list[str] = Field(default_factory=list)
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: int = 0


def _parse_pytest_output(stdout: str, stderr: str, exit_code: int) -> TestResult:
    combined = f"{stdout}\n{stderr}"
    passed_match = _PASSED_RE.search(combined)
    total = int(passed_match.group(1)) if passed_match else 0
    failed = _FAILED_LINE_RE.findall(combined)
    error_message = None
    if exit_code != 0 and not failed:
        error_message = stderr.strip() or stdout.strip() or "pytest failed"
    return TestResult(
        passed=exit_code == 0,
        total_tests=total,
        failed_tests=failed,
        error_message=error_message,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
    )


def run_tests(target_path: str, workspace: Path, timeout_s: int = 30) -> TestResult:
    """Run pytest in sandbox; parse output and apply truncation."""
    workspace = workspace.resolve()
    target = (workspace / target_path).resolve()
    if not str(target).startswith(str(workspace)):
        return TestResult(
            passed=False,
            error_message="target path outside workspace",
            exit_code=-1,
        )

    rel = target.relative_to(workspace).as_posix()
    cmd = f'"{sys.executable}" -m pytest "{rel}" -q --tb=short'
    started = time.perf_counter()
    proc = safe_execute(cmd, workspace, timeout_s=timeout_s)
    duration_ms = int((time.perf_counter() - started) * 1000)

    if proc.blocked:
        return TestResult(
            passed=False,
            error_message=proc.message,
            exit_code=proc.exit_code,
            duration_ms=duration_ms,
        )

    stdout = truncate(proc.stdout, "pytest_run")
    stderr = truncate(proc.stderr, "pytest_run")
    result = _parse_pytest_output(stdout, stderr, proc.exit_code)
    result.duration_ms = duration_ms
    return result
