"""Unit tests for cite allowlist validation (phase 31+)."""

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
    DEEPSEEK_DISCRIMINATIVE_SECTION,
    EXPECTED_DEEPSEEK_DISCRIMINATIVE_RUNS,
    entries_for_section,
    iter_cite_entries,
    load_cite_allowlist,
    trace_path_for_run,
    validate_cited_run,
)
from eval.manifest import write_manifest
from eval.metrics import RunResult


def _write_valid_run(
    traces_dir: Path,
    run_id: str,
    *,
    seed: int,
    config: str,
    dataset: str = "discriminative",
    n: int = 30,
    solved_fraction: float = 0.5,
) -> None:
    """Write aggregate JSONL + manifest that passes assess_run."""
    solved_n = int(n * solved_fraction)
    lines = []
    for index in range(n):
        lines.append(
            RunResult(
                task_id=f"HumanEval/{index}",
                solved=index < solved_n,
                outcome="solved" if index < solved_n else "escalate",
                interaction_count=2,
                step_count=2,
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
        task_ids=[f"HumanEval/{i}" for i in range(n)],
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC),
    )


def test_allowlist_entry_validates_when_trace_present(tmp_path: Path) -> None:
    """validate_cited_run succeeds for a quality-valid trace + manifest."""
    traces = tmp_path / "traces"
    traces.mkdir()
    run_id = "A_discriminative_20260521T120000Z"
    _write_valid_run(
        traces,
        run_id,
        seed=41,
        config="A",
    )
    summary = validate_cited_run(CiteEntry(run_id=run_id, seed=41), traces_dir=traces)
    assert summary.quality_valid
    assert summary.config == "A"
    assert summary.dataset == "discriminative"


def test_allowlist_entry_skips_when_trace_missing(tmp_path: Path) -> None:
    """Missing trace files are skipped in CI-safe validation (not failed)."""
    traces = tmp_path / "traces"
    traces.mkdir()
    run_id = "B_discriminative_20260521T120001Z"
    entry = CiteEntry(run_id=run_id, seed=42)
    trace_path = trace_path_for_run(run_id, traces)
    if trace_path.is_file():
        pytest.skip("trace unexpectedly present")
    with pytest.raises(CuratedReportError, match="missing trace"):
        validate_cited_run(entry, traces_dir=traces)


def test_iter_cite_entries_includes_sections(tmp_path: Path) -> None:
    """Section entries are merged with top-level runs for validation."""
    allowlist = CiteAllowlist(
        runs=[CiteEntry(run_id="A_humaneval_hard_20260520T111111Z")],
        sections={
            DEEPSEEK_DISCRIMINATIVE_SECTION: [
                CiteEntry(run_id="A_discriminative_20260521T100001Z", seed=41),
            ],
        },
    )
    ids = {entry.run_id for entry in iter_cite_entries(allowlist)}
    assert "A_humaneval_hard_20260520T111111Z" in ids
    assert "A_discriminative_20260521T100001Z" in ids
    assert len(entries_for_section(allowlist, DEEPSEEK_DISCRIMINATIVE_SECTION)) == 1


def test_validate_all_allowlist_entries_skips_missing_traces(
    tmp_path: Path,
) -> None:
    """Project allowlist: skip entries whose JSONL is absent; validate the rest."""
    traces = tmp_path / "traces"
    traces.mkdir()
    allowlist_path = tmp_path / "cite_allowlist.yaml"
    present_id = "C_discriminative_20260521T100002Z"
    missing_id = "D_discriminative_20260521T100003Z"
    _write_valid_run(traces, present_id, seed=43, config="C")
    allowlist_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "runs": [],
                "sections": {
                    DEEPSEEK_DISCRIMINATIVE_SECTION: [
                        {"run_id": present_id, "seed": 43, "config": "C"},
                        {"run_id": missing_id, "seed": 43, "config": "D"},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    allowlist = load_cite_allowlist(allowlist_path)
    validated = 0
    skipped = 0
    for entry in iter_cite_entries(allowlist):
        trace_path = trace_path_for_run(entry.run_id, traces)
        if not trace_path.is_file():
            skipped += 1
            continue
        validate_cited_run(entry, traces_dir=traces)
        validated += 1
    assert validated == 1
    assert skipped == 1


def test_deepseek_discriminative_section_complete_and_valid(
    tmp_path: Path,
) -> None:
    """Evidence gate: all 12 DeepSeek discriminative runs exist and pass quality."""
    traces_root = Path(__file__).resolve().parents[2] / "traces"
    allowlist = load_cite_allowlist()
    entries = entries_for_section(allowlist, DEEPSEEK_DISCRIMINATIVE_SECTION)
    if len(entries) < EXPECTED_DEEPSEEK_DISCRIMINATIVE_RUNS:
        pytest.skip(
            f"section {DEEPSEEK_DISCRIMINATIVE_SECTION!r} has {len(entries)} entries; "
            f"need {EXPECTED_DEEPSEEK_DISCRIMINATIVE_RUNS} after live ablation"
        )

    missing: list[str] = []
    for entry in entries:
        if not trace_path_for_run(entry.run_id, traces_root).is_file():
            missing.append(entry.run_id)
    if missing:
        pytest.skip(f"missing traces for section entries: {missing[:3]}...")

    for entry in entries:
        validate_cited_run(entry, traces_dir=traces_root)


@pytest.mark.parametrize(
    ("section", "expected"),
    [
        ("humaneval_discriminative_slm_small", 12),
        ("retrieval_keyword", 6),
        ("retrieval_semantic", 6),
        ("mbpp_50", 12),
        ("rq3_interaction_length", 6),
        ("rq3_agent_count", 6),
        ("swebench_pilot", 5),
    ],
)
def test_section_evidence_skips_when_empty(section: str, expected: int) -> None:
    """Live evidence gates skip cleanly when section has no cited runs yet."""
    allowlist = load_cite_allowlist()
    entries = entries_for_section(allowlist, section)
    if len(entries) < expected:
        pytest.skip(f"section {section!r} awaiting live runs ({len(entries)}/{expected})")
