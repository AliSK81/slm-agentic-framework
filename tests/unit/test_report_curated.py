"""Unit tests for curated report generation and repro bundle (phase 27)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from eval.curated import (
    CiteAllowlist,
    CiteEntry,
    CuratedReportError,
    build_curated_summaries,
    load_cite_allowlist,
)
from eval.manifest import write_manifest
from eval.metrics import RunResult
from eval.metrics.ci import mean_ci_95
from scripts.generate_report import generate_report
from scripts.make_repro_bundle import make_repro_bundle


def _write_run(
    traces_dir: Path,
    run_id: str,
    *,
    seed: int,
    config: str,
    dataset: str,
    solved_fraction: float,
    interaction_count: int = 2,
) -> None:
    """Write a valid aggregate JSONL + manifest for one cited run."""
    n = 5
    solved_n = int(n * solved_fraction)
    lines = []
    for index in range(n):
        lines.append(
            RunResult(
                task_id=f"task-{index}",
                solved=index < solved_n,
                outcome="solved" if index < solved_n else "escalate",
                interaction_count=interaction_count,
                step_count=interaction_count,
            ).model_dump()
        )
    trace_path = traces_dir / f"{run_id}.jsonl"
    trace_path.write_text(
        "\n".join(json.dumps(row) for row in lines) + "\n",
        encoding="utf-8",
    )
    write_manifest(
        run_id,
        traces_dir=traces_dir,
        config=config,
        dataset=dataset,
        n=n,
        seed=seed,
        provider="deepseek",
        planner_profile="deepseek-v4-flash",
        executor_profile="deepseek-v4-flash",
        git_sha="abc1234",
        task_ids=[f"task-{i}" for i in range(n)],
        created_at=datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC),
    )


def test_curated_report_excludes_non_allowlisted_runs(tmp_path: Path) -> None:
    """Only allowlisted run ids appear in curated summaries."""
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_run(
        traces,
        "A_humaneval_hard_20260520T111111Z",
        seed=42,
        config="A",
        dataset="humaneval_hard",
        solved_fraction=1.0,
    )
    _write_run(
        traces,
        "B_humaneval_hard_20260520T222222Z",
        seed=42,
        config="B",
        dataset="humaneval_hard",
        solved_fraction=0.0,
    )

    allowlist_path = tmp_path / "allowlist.yaml"
    allowlist_path.write_text(
        yaml.dump(
            {
                "version": 1,
                "excluded_run_ids": [],
                "runs": [
                    {
                        "run_id": "A_humaneval_hard_20260520T111111Z",
                        "seed": 42,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    groups = build_curated_summaries(
        load_cite_allowlist(allowlist_path),
        traces_dir=traces,
    )
    assert len(groups) == 1
    assert groups[0].config == "A"
    assert groups[0].run_ids == ["A_humaneval_hard_20260520T111111Z"]

    report = generate_report(
        traces,
        output_path=tmp_path / "report.md",
        curated=True,
        allowlist_path=allowlist_path,
        include_all_traces=True,
    )
    text = report.read_text(encoding="utf-8")
    assert "A_humaneval_hard_20260520T111111Z" in text
    assert "B_humaneval_hard_20260520T222222Z" not in text.split("## Curated results")[1].split("## Aggregate")[0]


def test_report_fails_on_cited_run_missing_manifest(tmp_path: Path) -> None:
    """Missing manifest for a cited run raises CuratedReportError."""
    traces = tmp_path / "traces"
    traces.mkdir()
    run_id = "D_humaneval_hard_20260520T333333Z"
    _write_run(traces, run_id, seed=42, config="D", dataset="humaneval_hard", solved_fraction=1.0)
    (traces / f"{run_id}.manifest.json").unlink()

    allowlist = CiteAllowlist(runs=[CiteEntry(run_id=run_id, seed=42)])
    with pytest.raises(CuratedReportError, match="missing manifest"):
        build_curated_summaries(allowlist, traces_dir=traces)


def test_report_rejects_cited_run_that_failed_quality_gate(tmp_path: Path) -> None:
    """Runs with too many zero-interaction tasks fail the quality gate."""
    traces = tmp_path / "traces"
    traces.mkdir()
    run_id = "C_humaneval_hard_20260520T444444Z"
    trace = traces / f"{run_id}.jsonl"
    trace.write_text(
        json.dumps(
            RunResult(
                task_id="t0",
                solved=False,
                outcome="escalate",
                interaction_count=0,
            ).model_dump()
        )
        + "\n",
        encoding="utf-8",
    )
    write_manifest(
        run_id,
        traces_dir=traces,
        config="C",
        dataset="humaneval_hard",
        n=1,
        seed=42,
        provider="deepseek",
        planner_profile="p",
        executor_profile="e",
        git_sha="abc1234",
        task_ids=["t0"],
        created_at=datetime(2026, 5, 20, tzinfo=UTC),
    )

    allowlist = CiteAllowlist(runs=[CiteEntry(run_id=run_id, seed=42)])
    with pytest.raises(CuratedReportError, match="quality gate"):
        build_curated_summaries(allowlist, traces_dir=traces)


def test_ci_computed_across_seeds() -> None:
    """Two seed SR values yield a non-zero 95% CI margin."""
    ci = mean_ci_95([90.0, 100.0])
    assert ci["n"] == 2
    assert ci["mean"] == 95.0
    assert ci["margin"] > 0.0
    assert ci["ci_low"] < ci["mean"] < ci["ci_high"]


def test_ci_computed_across_seeds_in_curated_group(tmp_path: Path) -> None:
    """Curated group with two seeds exposes SR mean ± CI in summaries."""
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_run(
        traces,
        "A_humaneval_hard_20260520T100001Z",
        seed=41,
        config="A",
        dataset="humaneval_hard",
        solved_fraction=0.8,
    )
    _write_run(
        traces,
        "A_humaneval_hard_20260520T100002Z",
        seed=42,
        config="A",
        dataset="humaneval_hard",
        solved_fraction=1.0,
    )
    allowlist = CiteAllowlist(
        runs=[
            CiteEntry(run_id="A_humaneval_hard_20260520T100001Z", seed=41),
            CiteEntry(run_id="A_humaneval_hard_20260520T100002Z", seed=42),
        ]
    )
    groups = build_curated_summaries(allowlist, traces_dir=traces)
    assert len(groups) == 1
    assert groups[0].sr_ci["n"] == 2
    assert groups[0].sr_ci["margin"] > 0.0


def test_repro_bundle_contains_no_secrets(tmp_path: Path) -> None:
    """Repro bundle copies cited artifacts without secret-like content."""
    traces = tmp_path / "traces"
    traces.mkdir()
    run_id = "D_humaneval_hard_20260520T555555Z"
    _write_run(
        traces,
        run_id,
        seed=42,
        config="D",
        dataset="humaneval_hard",
        solved_fraction=1.0,
    )
    allowlist_path = tmp_path / "allowlist.yaml"
    allowlist_path.write_text(
        yaml.dump({"version": 1, "runs": [{"run_id": run_id, "seed": 42}]}),
        encoding="utf-8",
    )

    bundle = make_repro_bundle(
        allowlist_path=allowlist_path,
        traces_dir=traces,
        output_dir=tmp_path / "bundle",
    )
    index = (bundle / "MANIFEST_INDEX.md").read_text(encoding="utf-8").lower()
    assert "sk-" not in index
    assert "api_key" not in index
    assert (bundle / "runs" / f"{run_id}.jsonl").is_file()
    assert (bundle / "runs" / f"{run_id}.manifest.json").is_file()
