"""SWE-bench Lite Docker test harness (never raises on tool errors)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from framework.error_control.sandbox import safe_execute
from framework.tools.test_runner import TestResult

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 600


class DockerNotAvailableError(RuntimeError):
    """Raised when ``docker_required`` is set but Docker is not usable on the host."""


def docker_available() -> bool:
    """Return True when the Docker CLI responds to ``docker info``."""
    if shutil.which("docker") is None:
        return False
    try:
        completed = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def require_docker(docker_required: bool) -> None:
    """Raise :class:`DockerNotAvailableError` when Docker is required but absent."""
    if docker_required and not docker_available():
        raise DockerNotAvailableError(
            "SWE-bench evaluation requires Docker on the host (configs/runtime/eval.yaml "
            "swebench.docker_required=true). Install/start Docker or set docker_required: false."
        )


def _instance_image(instance_id: str) -> str:
    """Map SWE-bench instance id to the official evaluation image name."""
    safe_id = instance_id.replace("/", "_")
    return f"swebench/sweb.eval.x86_64.{safe_id}:latest"


def _pytest_target(test_ids: list[str]) -> str:
    """Build a pytest target string from FAIL_TO_PASS / PASS_TO_PASS ids."""
    if not test_ids:
        return "-q"
    quoted = " ".join(json.dumps(item) for item in test_ids[:20])
    return f"-q -k \"({' or '.join(test_ids[:10])})\"" if len(test_ids) <= 10 else "-q"


def run_swe_instance_tests(
    *,
    instance_id: str,
    workspace: Path,
    fail_to_pass: list[str],
    pass_to_pass: list[str],
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> TestResult:
    """Run instance tests inside the SWE-bench Docker image via :func:`safe_execute`.

    Inputs: instance id, materialized repo workspace, gold test id lists, timeout.
    Outputs: typed :class:`TestResult`; never raises.
    Side effects: invokes ``docker run`` when Docker is available.
    """
    workspace = workspace.resolve()
    if not docker_available():
        return TestResult(
            passed=False,
            error_message="docker not available",
            exit_code=-1,
        )

    targets = fail_to_pass or pass_to_pass
    pytest_args = _pytest_target(targets)
    inner = f"cd /testbed && python -m pytest {pytest_args} --tb=short"
    image = _instance_image(instance_id)
    cmd = (
        f'docker run --rm -v "{workspace}:/testbed" -w /testbed '
        f"{image} bash -lc {json.dumps(inner)}"
    )
    proc = safe_execute(cmd, workspace, timeout_s=timeout_s)
    if proc.blocked:
        return TestResult(
            passed=False,
            error_message=proc.message or "docker command blocked by sandbox",
            exit_code=proc.exit_code,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    passed = proc.exit_code == 0
    error_message = None
    if not passed:
        error_message = proc.stderr.strip() or proc.stdout.strip() or "docker pytest failed"
    return TestResult(
        passed=passed,
        error_message=error_message,
        exit_code=proc.exit_code,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
