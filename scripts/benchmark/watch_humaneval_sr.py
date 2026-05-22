"""Read-only live HumanEval SR for the current run (does not interrupt pytest)."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _latest_e2e_log() -> Path | None:
    logs = sorted((_ROOT / "logs").glob("e2e_*.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def _run_cutoff_from_log(log: Path) -> float:
    text = log.read_text(encoding="utf-8")
    match = re.search(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO eval.datasets.humaneval_adapter: Loaded 20",
        text,
    )
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
    return log.stat().st_mtime - 60.0


def report(log: Path | None = None) -> int:
    log = log or _latest_e2e_log()
    if log is None or not log.is_file():
        print("No logs/e2e_*.log found.")
        return 1

    cutoff = _run_cutoff_from_log(log)
    text = log.read_text(encoding="utf-8")
    started = re.findall(r"Evaluating humaneval / (HumanEval/\d+)", text)
    current = started[-1] if started else "—"
    # Only tasks that have begun in *this* log (avoids old trace files on disk).
    begun_ids = list(dict.fromkeys(started))
    finished_ids = set(begun_ids[:-1]) if len(begun_ids) > 1 else set()

    per_task = _ROOT / "traces" / "per_task" / "D" / "humaneval"
    by_id: dict[str, dict] = {}
    if per_task.is_dir():
        for task_id in finished_ids:
            slug = task_id.replace("/", "_")
            path = per_task / f"{slug}.json"
            if path.is_file() and path.stat().st_mtime >= cutoff:
                by_id[task_id] = json.loads(path.read_text(encoding="utf-8"))

    completed = len(by_id)
    solved = sum(1 for r in by_id.values() if r.get("solved"))
    escalate = sum(1 for r in by_id.values() if r.get("outcome") == "escalate")
    unres = sum(1 for r in by_id.values() if r.get("outcome") == "unresolvable")
    sr = (100.0 * solved / completed) if completed else 0.0

    print("=== HumanEval config D — live (read-only) ===")
    print(f"Framework log: {log}")
    print(f"Tasks begun: {len(begun_ids)}/20")
    print(f"Currently on: {current}")
    print(f"Finished (trace written): {completed}/{max(len(begun_ids) - 1, 0)}")
    if completed:
        print(f"SR so far: {sr:.1f}%  ({solved}/{completed} solved)")
        print(f"escalate={escalate}  unresolvable={unres}")
    print(f"Log last updated: {datetime.fromtimestamp(log.stat().st_mtime)}")
    return 0


if __name__ == "__main__":
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    raise SystemExit(report(arg))
