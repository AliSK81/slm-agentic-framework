"""Pluggable workspace verification for sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from framework.tools.compile_check import py_compile_check


class EvaluationResult(BaseModel):
    """Normalized outcome of verifying a workspace after executor work."""

    passed: bool
    failed_tests: list[str] = Field(default_factory=list)
    error_message: str | None = None
    exit_code: int | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a dict compatible with workflow ``last_evaluation``."""
        return self.model_dump(exclude_none=True)


@runtime_checkable
class Verifier(Protocol):
    """Protocol for post-execute workspace checks."""

    def evaluate(self, workspace: Path) -> EvaluationResult:
        """Verify the workspace; never raises on tool-level failures."""


class TestCodeVerifier:
    """Run hidden assertion code via :func:`evaluate_workspace`."""

    __test__ = False  # not a pytest test class

    def __init__(self, test_code: str) -> None:
        self._test_code = test_code

    def evaluate(self, workspace: Path) -> EvaluationResult:
        from framework.orchestration.session import evaluate_workspace

        raw = evaluate_workspace(workspace, self._test_code)
        return EvaluationResult(
            passed=bool(raw.get("passed")),
            failed_tests=list(raw.get("failed_tests") or []),
            error_message=raw.get("error_message"),
            exit_code=raw.get("exit_code"),
            error=raw.get("error"),
        )


class NoOpVerifier:
    """Compile non-test ``*.py`` files; pass when there is nothing to compile."""

    def evaluate(self, workspace: Path) -> EvaluationResult:
        py_files = sorted(
            p
            for p in workspace.glob("*.py")
            if p.is_file() and not p.name.startswith("test_")
        )
        if not py_files:
            return EvaluationResult(passed=True)

        errors: list[str] = []
        for path in py_files:
            result = py_compile_check(str(path))
            if not result.ok:
                errors.extend(result.errors)
        if errors:
            return EvaluationResult(
                passed=False,
                error_message="; ".join(errors),
                failed_tests=[p.name for p in py_files],
            )
        return EvaluationResult(passed=True)


def resolve_verifier(
    test_code: str,
    verifier: Verifier | None,
) -> Verifier:
    """Pick the effective verifier for a session or turn.

    Args:
        test_code: Hidden test assertions (thesis eval path).
        verifier: Explicit verifier override (custom).

    Returns:
        ``TestCodeVerifier`` when ``test_code`` is non-empty and no override;
        otherwise ``NoOpVerifier`` when both are empty.
    """
    if verifier is not None:
        return verifier
    if test_code.strip():
        return TestCodeVerifier(test_code)
    return NoOpVerifier()
