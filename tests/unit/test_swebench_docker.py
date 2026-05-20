"""Unit tests for SWE-bench repo materialization and Docker harness."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eval.datasets.swebench_adapter import SWEBenchTask, materialize_instance_workspace
from eval.swe_docker import (
    DockerNotAvailableError,
    docker_available,
    require_docker,
    run_swe_instance_tests,
)
from framework.error_control.sandbox import SAFE_COMMANDS
from framework.tools.test_runner import TestResult


def _sample_task() -> SWEBenchTask:
    return SWEBenchTask(
        task_id="django__django-11099",
        repo="django/django",
        base_commit="abcdef1234567890",
        problem_statement="Fix the bug.",
        fail_to_pass=["tests.test_foo.TestCase.test_bar"],
        pass_to_pass=["tests.test_foo.TestCase.test_ok"],
    )


def test_swebench_instance_materializes_repo(tmp_path: Path) -> None:
    """Git clone and checkout are invoked to materialize the instance workspace."""
    task = _sample_task()
    workspace = tmp_path / "ws"

    with patch("eval.datasets.swebench_adapter.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        repo_dir = materialize_instance_workspace(task, workspace)

    assert repo_dir == workspace / "repo"
    assert mock_run.call_count >= 2
    clone_args = mock_run.call_args_list[0][0][0]
    assert clone_args[0] == "git"
    assert "clone" in clone_args


def test_swe_docker_skips_cleanly_when_docker_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When Docker is missing, grading returns a failed TestResult without raising."""
    monkeypatch.setattr("eval.swe_docker.docker_available", lambda: False)
    result = run_swe_instance_tests(
        instance_id="django__django-11099",
        workspace=tmp_path,
        fail_to_pass=["tests.test_x"],
        pass_to_pass=[],
    )
    assert isinstance(result, TestResult)
    assert result.passed is False
    assert result.error_message == "docker not available"


def test_swe_result_is_typed_testresult(monkeypatch: pytest.MonkeyPatch) -> None:
    """Docker grading maps sandbox success to a passing TestResult."""
    from framework.error_control.sandbox import SubprocessResult

    monkeypatch.setattr("eval.swe_docker.docker_available", lambda: True)
    monkeypatch.setattr(
        "eval.swe_docker.safe_execute",
        lambda *_a, **_k: SubprocessResult(ok=True, stdout="1 passed", stderr="", exit_code=0),
    )
    result = run_swe_instance_tests(
        instance_id="django__django-11099",
        workspace=Path("."),
        fail_to_pass=["tests.test_x"],
        pass_to_pass=[],
    )
    assert isinstance(result, TestResult)
    assert result.passed is True
    assert result.exit_code == 0


def test_require_docker_raises_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """require_docker surfaces DockerNotAvailableError for CI without Docker."""
    monkeypatch.setattr("eval.swe_docker.docker_available", lambda: False)
    with pytest.raises(DockerNotAvailableError):
        require_docker(True)


def test_sandbox_allowlists_docker() -> None:
    """Phase-21 extends the sandbox allow-list with the docker executable."""
    assert "docker" in SAFE_COMMANDS
