"""Unit tests for eval manifest and --task-id CLI path."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from eval.config import AblationFlags
from eval.manifest import (
    RunManifest,
    assert_manifest_has_no_secrets,
    resolve_git_sha,
    write_manifest,
)
from eval.metrics import RunResult
from eval.run_eval import run_eval


def test_manifest_written_with_git_sha_and_no_secrets(tmp_path: Path) -> None:
    """Manifest includes git SHA and contains no secret-like fields or values."""
    path = write_manifest(
        "D_humaneval_test",
        traces_dir=tmp_path,
        config="D",
        dataset="humaneval",
        n=1,
        seed=42,
        provider="deepseek",
        planner_profile="deepseek_planner",
        executor_profile="deepseek_executor",
        git_sha=resolve_git_sha(),
        task_ids=["HumanEval/0"],
        ablation_flags={"memory": True, "control": True, "error_control": True},
        created_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["git_sha"] not in ("", "unknown") or payload["git_sha"] == "unknown"
    assert len(payload["git_sha"]) >= 7
    assert_manifest_has_no_secrets(payload)
    assert "api_key" not in path.read_text(encoding="utf-8").lower()


def test_manifest_records_ablation_flags_for_config_D(tmp_path: Path) -> None:
    """Config D manifest records all ablation flags enabled."""
    flags = AblationFlags(memory=True, control=True, error_control=True)
    manifest = RunManifest(
        run_id="D_humaneval_test",
        config="D",
        dataset="humaneval",
        n=5,
        seed=42,
        provider="deepseek",
        planner_profile="deepseek_planner",
        executor_profile="deepseek_executor",
        git_sha="abc123",
        task_ids=["HumanEval/0"],
        ablation_flags=flags.model_dump(),
        created_at=datetime.now(UTC),
    )

    assert manifest.ablation_flags == {
        "memory": True,
        "control": True,
        "error_control": True,
    }


def test_run_eval_task_id_runs_only_named_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--task-id path runs exactly the named tasks without sampling."""
    monkeypatch.setattr("eval.run_eval._traces_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "eval.run_eval.manifest_provider_and_profiles",
        lambda: ("deepseek", "deepseek_planner", "deepseek_executor"),
    )
    monkeypatch.setattr("eval.run_eval.resolve_git_sha", lambda _root=None: "deadbeef")

    run_calls: list[str] = []

    def mock_load_by_ids(
        dataset_name: str,
        ids: list[str],
    ) -> list[tuple[str, str, list[str], str, str | None]]:
        assert ids == ["HumanEval/0"]
        return [("HumanEval/0", "goal", ["c"], "assert True", None)]

    def mock_run_single_task(task_id: str, *args: object, **kwargs: object) -> RunResult:
        run_calls.append(task_id)
        return RunResult(
            task_id=task_id,
            solved=False,
            outcome="dry_run",
            interaction_count=0,
            trace_path="traces/x.json",
        )

    load_tasks = MagicMock()
    monkeypatch.setattr("eval.run_eval._load_tasks_by_ids", mock_load_by_ids)
    monkeypatch.setattr("eval.run_eval._load_tasks", load_tasks)
    monkeypatch.setattr("eval.run_eval._run_single_task", mock_run_single_task)

    summary = run_eval(
        "D",
        "humaneval",
        task_ids=["HumanEval/0"],
        dry_run=True,
    )

    assert summary["n"] == 1
    assert run_calls == ["HumanEval/0"]
    load_tasks.assert_not_called()
    manifest_path = Path(summary["manifest_file"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["task_ids"] == ["HumanEval/0"]
    assert manifest["config"] == "D"
