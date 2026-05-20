"""Append-only decision JSONL for eval runs (joinable on task_id)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from framework.memory.stores import DecisionEntry

logger = logging.getLogger(__name__)


class StreamedDecisionLine(BaseModel):
    """One decision row in ``traces/decisions/{run_id}.jsonl``."""

    task_id: str
    session_id: str
    step_index: int
    kind: str
    self_check_verdict: str
    decision_id: str = ""
    by_agent: str = ""
    rationale: str = ""
    self_check_issues: list[str] = Field(default_factory=list)
    payload_hash: str = ""


def _payload_hash(payload: dict[str, object]) -> str:
    """Stable short hash of decision payload for oscillation detection."""
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class DecisionLogWriter:
    """Append decision lines to a run-scoped JSONL file."""

    def __init__(self, path: Path) -> None:
        self._path = path.resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, entry: DecisionEntry, *, task_id: str) -> None:
        """Write one streamed line; never raises on I/O failure."""
        line = StreamedDecisionLine(
            task_id=task_id,
            session_id=entry.session_id,
            step_index=entry.step_index,
            kind=entry.kind,
            self_check_verdict=entry.self_check.verdict,
            decision_id=entry.decision_id,
            by_agent=entry.by_agent,
            rationale=entry.rationale[:500],
            self_check_issues=[issue.kind for issue in entry.self_check.issues],
            payload_hash=_payload_hash(entry.payload),
        )
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line.model_dump(mode="json"), default=str) + "\n")
        except OSError as exc:
            logger.warning("Could not append decision log %s: %s", self._path, exc)


def load_streamed_decisions(path: str | Path) -> list[StreamedDecisionLine]:
    """Load all lines from a decision JSONL file."""
    file_path = Path(path)
    if not file_path.is_file():
        return []
    rows: list[StreamedDecisionLine] = []
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        rows.append(StreamedDecisionLine.model_validate(json.loads(raw)))
    return rows


def decisions_path_for_run(traces_dir: Path, run_id: str) -> Path:
    """Standard path: ``traces/decisions/{run_id}.jsonl``."""
    return traces_dir / "decisions" / f"{run_id}.jsonl"
