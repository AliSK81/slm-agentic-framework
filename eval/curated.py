"""Curated allowlist loading and validation for reporting."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from eval.manifest import RunManifest, assert_manifest_has_no_secrets
from eval.metrics import RunResult, compute_cer, compute_sr
from eval.metrics.ci import MeanCI95, format_mean_pm_ci, mean_ci_95
from eval.run_quality import assess_run

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_ALLOWLIST = _PROJECT_ROOT / "configs" / "reporting" / "cite_allowlist.yaml"
_LEGACY_ALLOWLIST = _PROJECT_ROOT / "configs" / "cite_allowlist.yaml"
_DEFAULT_ALLOWLIST = _RUNTIME_ALLOWLIST if _RUNTIME_ALLOWLIST.is_file() else _LEGACY_ALLOWLIST

DEEPSEEK_DISCRIMINATIVE_SECTION = "humaneval_discriminative_deepseek"
SLM_SMALL_DISCRIMINATIVE_SECTION = "humaneval_discriminative_slm_small"
RETRIEVAL_KEYWORD_SECTION = "retrieval_keyword"
RETRIEVAL_SEMANTIC_SECTION = "retrieval_semantic"
MBPP_50_SECTION = "mbpp_50"
RQ3_INTERACTION_LENGTH_SECTION = "rq3_interaction_length"
RQ3_AGENT_COUNT_SECTION = "rq3_agent_count"
SWEBENCH_PILOT_SECTION = "swebench_pilot"
EXPECTED_DEEPSEEK_DISCRIMINATIVE_RUNS = 12  # 4 configs × 3 seeds

_API_KEY_PATTERN = re.compile(r"sk-[a-zA-Z0-9]{10,}")
_FORBIDDEN_VALUE_MARKERS = ("api_key", "bearer ", "password", "secret_key")


class CuratedReportError(RuntimeError):
    """Raised when an allowlisted run fails manifest or quality validation."""


class CiteEntry(BaseModel):
    """One allowlisted run to cite in reports."""

    run_id: str
    seed: int | None = None
    config: str | None = None
    dataset: str | None = None
    note: str = ""


class CiteAllowlist(BaseModel):
    """Canonical runs for results-chapter automation."""

    version: int = 1
    excluded_run_ids: list[str] = Field(default_factory=list)
    runs: list[CiteEntry] = Field(default_factory=list)
    sections: dict[str, list[CiteEntry]] = Field(default_factory=dict)


def iter_cite_entries(allowlist: CiteAllowlist) -> list[CiteEntry]:
    """Return all allowlisted entries (top-level ``runs`` plus every ``sections`` block)."""
    entries = list(allowlist.runs)
    for section_runs in allowlist.sections.values():
        entries.extend(section_runs)
    return entries


def entries_for_section(allowlist: CiteAllowlist, section: str) -> list[CiteEntry]:
    """Return entries for a named section (empty when the section is absent)."""
    return list(allowlist.sections.get(section, []))


class CitedRunSummary(BaseModel):
    """Validated metrics for one allowlisted run."""

    run_id: str
    trace_path: str
    manifest_path: str
    seed: int
    config: str
    dataset: str
    sr: float
    cer: float
    n: int
    quality_valid: bool = True


class CuratedGroupSummary(BaseModel):
    """Aggregated SR/CER across seeds for one (config, dataset) pair."""

    config: str
    dataset: str
    seeds: list[int]
    run_ids: list[str]
    sr_ci: MeanCI95
    cer_ci: MeanCI95
    runs: list[CitedRunSummary]


def load_cite_allowlist(path: Path | None = None) -> CiteAllowlist:
    """Load ``configs/cite_allowlist.yaml``."""
    target = path or _DEFAULT_ALLOWLIST
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return CiteAllowlist.model_validate(raw)


def _parse_run_id(run_id: str) -> tuple[str, str]:
    """Parse ``D_humaneval_hard_20260520T131220Z`` into config and dataset."""
    match = re.match(r"^([ABCD])_(\w+)_", run_id)
    if match:
        return match.group(1), match.group(2)
    parts = run_id.split("_", 2)
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "?", "unknown"


def trace_path_for_run(run_id: str, traces_dir: Path) -> Path:
    """Resolve aggregate JSONL path for a run id."""
    return traces_dir / f"{run_id}.jsonl"


def manifest_path_for_run(run_id: str, traces_dir: Path) -> Path:
    """Resolve manifest JSON path for a run id."""
    return traces_dir / f"{run_id}.manifest.json"


def validate_cited_run(
    entry: CiteEntry,
    *,
    traces_dir: Path,
) -> CitedRunSummary:
    """Ensure manifest exists, quality gate passes, and return run metrics.

    Raises:
        CuratedReportError: Missing trace/manifest or failed quality gate.
    """
    trace_path = trace_path_for_run(entry.run_id, traces_dir)
    manifest_path = manifest_path_for_run(entry.run_id, traces_dir)

    if not trace_path.is_file():
        raise CuratedReportError(f"cited run missing trace JSONL: {trace_path}")
    if not manifest_path.is_file():
        raise CuratedReportError(
            f"cited run missing manifest: {manifest_path} (run_id={entry.run_id})"
        )

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        assert_manifest_has_no_secrets(manifest_payload)
    except ValueError as exc:
        raise CuratedReportError(f"manifest failed secret scan: {exc}") from exc
    manifest = RunManifest.model_validate(manifest_payload)

    quality = assess_run(str(trace_path))
    if not quality.valid:
        raise CuratedReportError(
            f"cited run failed quality gate ({entry.run_id}): {quality.reason}"
        )

    rows: list[RunResult] = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(RunResult.model_validate(json.loads(line)))

    config = entry.config or manifest.config
    dataset = entry.dataset or manifest.dataset
    seed = entry.seed if entry.seed is not None else manifest.seed

    return CitedRunSummary(
        run_id=entry.run_id,
        trace_path=str(trace_path.resolve()),
        manifest_path=str(manifest_path.resolve()),
        seed=seed,
        config=config,
        dataset=dataset,
        sr=compute_sr(rows),
        cer=compute_cer(rows),
        n=len(rows),
        quality_valid=True,
    )


def build_curated_summaries(
    allowlist: CiteAllowlist,
    *,
    traces_dir: Path,
) -> list[CuratedGroupSummary]:
    """Validate all allowlisted runs and aggregate SR/CER with 95% CIs per config/dataset."""
    excluded = set(allowlist.excluded_run_ids)
    cited: list[CitedRunSummary] = []
    for entry in iter_cite_entries(allowlist):
        if entry.run_id in excluded:
            continue
        cited.append(validate_cited_run(entry, traces_dir=traces_dir))

    groups: dict[tuple[str, str], list[CitedRunSummary]] = {}
    for row in cited:
        key = (row.config, row.dataset)
        groups.setdefault(key, []).append(row)

    summaries: list[CuratedGroupSummary] = []
    for (config, dataset), rows in sorted(groups.items()):
        srs = [r.sr for r in rows]
        cers = [r.cer for r in rows]
        summaries.append(
            CuratedGroupSummary(
                config=config,
                dataset=dataset,
                seeds=sorted({r.seed for r in rows}),
                run_ids=[r.run_id for r in rows],
                sr_ci=mean_ci_95(srs),
                cer_ci=mean_ci_95(cers),
                runs=rows,
            )
        )
    return summaries


def assert_text_has_no_secrets(text: str, *, label: str) -> None:
    """Raise when file content looks like it contains API keys."""
    if _API_KEY_PATTERN.search(text):
        raise ValueError(f"secret-like API key pattern in {label}")
    lowered = text.lower()
    for marker in _FORBIDDEN_VALUE_MARKERS:
        if marker in lowered:
            raise ValueError(f"secret-like content in {label}: {marker}")


def collect_cited_artifacts(
    allowlist: CiteAllowlist,
    *,
    traces_dir: Path,
) -> list[tuple[Path, str]]:
    """Return ``(source_path, bundle_relative_name)`` pairs for allowlisted runs."""
    summaries = build_curated_summaries(allowlist, traces_dir=traces_dir)
    artifacts: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for group in summaries:
        for run in group.runs:
            trace = Path(run.trace_path)
            manifest = Path(run.manifest_path)
            for src in (trace, manifest):
                rel = f"runs/{src.name}"
                if rel not in seen:
                    artifacts.append((src, rel))
                    seen.add(rel)
            manifest_obj = RunManifest.model_validate(
                json.loads(manifest.read_text(encoding="utf-8"))
            )
            if manifest_obj.decisions_file:
                decisions = Path(manifest_obj.decisions_file)
                if decisions.is_file():
                    rel = f"decisions/{decisions.name}"
                    if rel not in seen:
                        artifacts.append((decisions, rel))
                        seen.add(rel)
    return artifacts
