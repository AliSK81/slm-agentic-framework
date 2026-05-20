"""Classify run outcomes and escalation reasons for qualitative reporting."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from eval.decision_log import load_streamed_decisions
from eval.manifest import RunManifest
from eval.metrics.sr import RunResult

OutcomeKind = Literal[
    "solved",
    "escalate",
    "max_steps_reached",
    "unresolvable",
    "other",
]


class TaxonomyCounts(BaseModel):
    """Outcome counts for one config (optionally per provider)."""

    config: str
    provider: str = ""
    dataset: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    total: int = 0


def classify_outcome(outcome: str) -> OutcomeKind:
    """Map raw outcome string to taxonomy label."""
    normalized = outcome.strip().lower()
    if normalized == "solved":
        return "solved"
    if normalized == "escalate":
        return "escalate"
    if normalized in ("max_steps_reached", "max_steps"):
        return "max_steps_reached"
    if normalized == "unresolvable":
        return "unresolvable"
    return "other"


def taxonomy_from_trace(
    trace_path: Path,
    *,
    config: str = "",
    provider: str = "",
    dataset: str = "",
) -> TaxonomyCounts:
    """Count outcome kinds for one aggregate JSONL trace."""
    counter: Counter[str] = Counter()
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = RunResult.model_validate(json.loads(line))
        counter[classify_outcome(row.outcome)] += 1

    manifest_path = trace_path.with_name(f"{trace_path.stem}.manifest.json")
    if manifest_path.is_file():
        manifest = RunManifest.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        config = config or manifest.config
        provider = provider or manifest.provider
        dataset = dataset or manifest.dataset
        decisions_path = manifest.decisions_file
        if decisions_path:
            path = Path(decisions_path)
            if path.is_file():
                for _line in load_streamed_decisions(path):
                    pass  # ensures decision JSONL is readable (not checkpoints)

    return TaxonomyCounts(
        config=config,
        provider=provider,
        dataset=dataset,
        counts=dict(counter),
        total=sum(counter.values()),
    )


def merge_taxonomies(rows: list[TaxonomyCounts]) -> list[TaxonomyCounts]:
    """Merge taxonomy rows by (provider, config, dataset)."""
    merged: dict[tuple[str, str, str], TaxonomyCounts] = {}
    for row in rows:
        key = (row.provider, row.config, row.dataset)
        if key not in merged:
            merged[key] = TaxonomyCounts(
                config=row.config,
                provider=row.provider,
                dataset=row.dataset,
                counts=dict(row.counts),
                total=row.total,
            )
            continue
        target = merged[key]
        for label, count in row.counts.items():
            target.counts[label] = target.counts.get(label, 0) + count
        target.total += row.total
    return list(merged.values())
