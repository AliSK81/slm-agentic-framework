"""SWE-bench Lite dataset adapter with repo materialization and Docker grading."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from eval.swe_docker import DockerNotAvailableError, docker_available, require_docker

logger = logging.getLogger(__name__)


class SWEBenchTask(BaseModel):
    """One SWE-bench Lite instance with gold test ids for Docker evaluation."""

    task_id: str
    repo: str
    base_commit: str
    problem_statement: str
    fail_to_pass: list[str] = Field(default_factory=list)
    pass_to_pass: list[str] = Field(default_factory=list)
    version: str = ""
    test_patch: str = ""
    patch: str = ""


class MaterializeError(RuntimeError):
    """Raised when a SWE-bench workspace cannot be checked out at ``base_commit``."""


def _parse_test_id_list(raw: Any) -> list[str]:
    """Parse FAIL_TO_PASS / PASS_TO_PASS from JSON string or list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [stripped]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return [str(parsed)]
    return [str(raw)]


def _load_swebench_rows() -> list[SWEBenchTask]:
    """Load the full SWE-bench Lite test split metadata."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("datasets package is required for SWE-bench loading") from exc

    dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    rows: list[SWEBenchTask] = []
    for row in dataset:
        rows.append(
            SWEBenchTask(
                task_id=str(row["instance_id"]),
                repo=str(row["repo"]),
                base_commit=str(row["base_commit"]),
                problem_statement=str(row["problem_statement"]),
                fail_to_pass=_parse_test_id_list(row.get("FAIL_TO_PASS")),
                pass_to_pass=_parse_test_id_list(row.get("PASS_TO_PASS")),
                version=str(row.get("version", "") or ""),
                test_patch=str(row.get("test_patch", "") or ""),
                patch=str(row.get("patch", "") or ""),
            )
        )
    return rows


def load_swebench_by_ids(task_ids: list[str]) -> list[SWEBenchTask]:
    """Load specific SWE-bench Lite tasks by ``task_id`` (order preserved)."""
    lookup = {task.task_id: task for task in _load_swebench_rows()}
    missing = [task_id for task_id in task_ids if task_id not in lookup]
    if missing:
        raise ValueError(f"Unknown SWE-bench task_id(s): {missing}")
    return [lookup[task_id] for task_id in task_ids]


def load_swebench(
    n: int = 30,
    seed: int = 42,
    *,
    docker_required: bool = True,
) -> list[SWEBenchTask]:
    """Load a sample of SWE-bench Lite tasks; optionally require Docker on the host."""
    from eval.datasets._sample import sample_items

    if docker_required:
        require_docker(docker_required=True)
    rows = _load_swebench_rows()
    sampled = sample_items(rows, n, seed)
    logger.info("Loaded %s SWE-bench Lite tasks (requested n=%s)", len(sampled), n)
    return sampled


def materialize_instance_workspace(task: SWEBenchTask, workspace: Path) -> Path:
    """Clone ``task.repo`` into ``workspace`` and checkout ``base_commit``.

    Inputs: task metadata and empty or partial workspace directory.
    Outputs: resolved workspace path containing the repo at base commit.
    Side effects: network git clone/fetch; writes under ``workspace``.
    """
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    repo_dir = workspace / "repo"
    repo_url = f"https://github.com/{task.repo}.git"

    if not (repo_dir / ".git").is_dir():
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(repo_dir)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if clone.returncode != 0:
            raise MaterializeError(
                f"git clone failed for {task.repo}: {clone.stderr.strip() or clone.stdout}"
            )

    fetch = subprocess.run(
        ["git", "-C", str(repo_dir), "fetch", "--depth", "1", "origin", task.base_commit],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    checkout = subprocess.run(
        ["git", "-C", str(repo_dir), "checkout", "--force", task.base_commit],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if checkout.returncode != 0:
        raise MaterializeError(
            f"git checkout {task.base_commit} failed: "
            f"{checkout.stderr.strip() or fetch.stderr.strip() or checkout.stdout}"
        )
    logger.info("Materialized %s at %s in %s", task.repo, task.base_commit, repo_dir)
    return repo_dir


def task_to_session(task: SWEBenchTask) -> tuple[str, list[str], str]:
    """Map a SWE-bench row to session goal, constraints, and interim pytest body."""
    goal = (
        f"Fix the issue in repository {task.repo} (base commit {task.base_commit}):\n\n"
        f"{task.problem_statement}"
    )
    constraints = [
        f"Work in the materialized repository under workspace/repo",
        f"FAIL_TO_PASS tests must pass after the fix: {', '.join(task.fail_to_pass[:5])}",
        "Final grading uses the SWE-bench Docker harness",
    ]
    test_code = (
        "# Interim session check; authoritative grading is Docker-based.\n"
        "assert True\n"
    )
    return goal, constraints, test_code


def docker_skip_reason() -> str | None:
    """Return a human-readable skip reason when Docker is required but missing."""
    if docker_available():
        return None
    return "Docker is not available on this host"
