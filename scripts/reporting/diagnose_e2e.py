"""Diagnose e2e test timing — per-task wall time, per-model latency, unique errors.

Usage:
  python scripts/diagnose_e2e.py <log_path>
  python scripts/diagnose_e2e.py logs/e2e_20260521T170814Z.log

Reads the e2e framework log, per_task/*.json results, manifest files, and session
SQLite DBs to build a timing breakdown table and error summary.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime
from glob import glob
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[2]


def _parse_events(log_path: str) -> list[dict]:
    """Parse e2e log into structured events."""
    events = []
    pat = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+([\w.]+):\s+(.*)"
    )
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = pat.match(line)
            if m:
                ts_str, level, logger, msg = m.groups()
                events.append({"ts": ts_str, "level": level, "logger": logger, "msg": msg})
    return events


def _parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _load_manifest(config: str, dataset: str, traces_dir: Path) -> dict | None:
    """Find the manifest file for a given config/dataset run."""
    pattern = str(traces_dir / f"{config}_{dataset}_*.manifest.json")
    files = sorted(glob(pattern))
    if not files:
        return None
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def _per_task_results(config: str, dataset: str) -> dict[str, dict]:
    results: dict[str, dict] = {}
    pat = str(_PROJECT / "traces" / "per_task" / config / dataset / "HumanEval_*.json")
    for f in sorted(glob(pat)):
        try:
            d = json.load(open(f, encoding="utf-8"))
            results[d["task_id"]] = d
        except Exception:
            pass
    return results


def _db_timings(session_id: str, data_dir: Path) -> dict | None:
    db_path = data_dir / f"{session_id}.db"
    if not db_path.is_file():
        return None
    db = sqlite3.connect(str(db_path))
    try:
        state_rows = db.execute(
            "SELECT created_at FROM memory_rows WHERE store='state' AND row_key LIKE '%:0' ORDER BY id LIMIT 1"
        ).fetchall()
        dec_rows = db.execute(
            "SELECT payload, created_at FROM memory_rows WHERE store='decisions' ORDER BY id"
        ).fetchall()
        report_rows = db.execute(
            "SELECT payload, created_at FROM memory_rows WHERE store='report_messages' ORDER BY id DESC LIMIT 1"
        ).fetchall()

        session_start = state_rows[0][0] if state_rows else None
        plan_ts = None
        for payload_str, ts in dec_rows:
            d = json.loads(payload_str)
            if d.get("kind") == "plan_step":
                plan_ts = ts
                break
        report_ts = report_rows[0][1] if report_rows else None

        result: dict = {}
        if session_start and plan_ts:
            result["plan_sec"] = (
                _parse_ts(plan_ts) - _parse_ts(session_start)
            ).total_seconds()
        if plan_ts and report_ts:
            result["exec_sec"] = (
                _parse_ts(report_ts) - _parse_ts(plan_ts)
            ).total_seconds()
        return result
    finally:
        db.close()


def diagnose(log_path: str) -> None:
    events = _parse_events(log_path)
    traces_dir = _PROJECT / "traces"

    # Discover all (config, dataset) runs from "Ablation config X on Y" or "Eval complete" lines
    runs: list[dict] = []  # {config, dataset, tasks: {id: {wall, session_id}}}
    current_run: dict | None = None
    eval_stack: list[tuple[str, str, str]] = []  # (task_id, config, start_ts)

    for ev in events:
        msg = ev["msg"]

        # "Ablation config A on humaneval_hard" or "Evaluating humaneval_hard / HumanEval/64"
        m = re.match(r"Ablation config (\w+) on (\w+)", msg)
        if m:
            current_run = {"config": m.group(1), "dataset": m.group(2), "tasks": {}}
            runs.append(current_run)
            continue

        m = re.match(r"Evaluating (\w+) / ([\w/]+)", msg)
        if m:
            dataset, task_id = m.group(1), m.group(2)
            cfg = current_run["config"] if current_run else "?"
            eval_stack.append((task_id, cfg, ev["ts"]))

        # Checkpoint signals end of a task's steps
        m = re.match(r"Checkpoint saved:.*(sess-\w+)_\d+\.json", msg)
        if m and eval_stack:
            task_id, cfg, start_ts = eval_stack[-1]
            sid = m.group(1)
            if current_run and cfg == current_run["config"]:
                current_run["tasks"][task_id] = {
                    "wall_start": start_ts,
                    "wall_end": ev["ts"],
                    "session_id": sid,
                    "config": cfg,
                    "errors": [],
                }
            # Don't pop — next Evaluating overwrites

        # Warnings/errors — attribute to current task
        if ev["level"] in ("WARNING", "ERROR") and eval_stack:
            task_id, cfg, _ = eval_stack[-1]
            if current_run and cfg == current_run["config"]:
                current_run["tasks"].setdefault(
                    task_id,
                    {"wall_start": "", "wall_end": "", "session_id": "", "config": cfg, "errors": []},
                )
                current_run["tasks"][task_id]["errors"].append(ev["msg"])

    # For each run, enrich with manifest data (session map) and per_task results
    # Collect errors globally from all events, grouped by config
    error_by_config: dict[str, list[str]] = {}
    current_cfg_for_errors = "?"
    for ev in events:
        m = re.match(r"Ablation config (\w+) on (\w+)", ev["msg"])
        if m:
            current_cfg_for_errors = m.group(1)
        if ev["level"] in ("WARNING", "ERROR"):
            error_by_config.setdefault(current_cfg_for_errors, []).append(ev["msg"])

    for run in runs:
        config, dataset = run["config"], run["dataset"]
        manifest = _load_manifest(config, dataset, traces_dir)
        per_task = _per_task_results(config, dataset)
        data_dir = traces_dir / "workspaces" / config / dataset / "data"

        # Apply session map from manifest if available
        session_map = manifest.get("task_to_session_map", {}) if manifest else {}
        for task_id in list(run["tasks"]):
            if task_id in session_map and not run["tasks"][task_id].get("session_id"):
                run["tasks"][task_id]["session_id"] = session_map[task_id]

        # --- Print ---
        print(f"\n=== Config {config} on {dataset} ===")
        hdr = f"{'Task':<14} {'Wall':>6s} {'Plan':>8s} {'Exec':>8s} {'#LLM':>5s} {'Ovrhd':>6s}  {'Result'}"
        print(hdr)
        print("-" * 75)

        solved = 0
        count = 0
        tw = te = tp = to = 0.0  # totals

        for task_id in sorted(run["tasks"]):
            t = run["tasks"][task_id]
            pt = per_task.get(task_id, {})
            db = _db_timings(t.get("session_id", ""), data_dir) if t.get("session_id") else None

            w_start = t.get("wall_start", "")
            w_end = t.get("wall_end", "")
            wall = (_parse_ts(w_end) - _parse_ts(w_start)).total_seconds() if w_start and w_end else 0

            lat = pt.get("latency_ms_total", 0) / 1000
            calls = pt.get("llm_calls", 0)
            ok = pt.get("solved", False)

            plan_s = db.get("plan_sec", 0) if db else 0
            exec_s = db.get("exec_sec", 0) if db else 0
            if not plan_s and not exec_s:
                # Fallback: estimate from latency
                plan_s = min(30, lat * 0.25)
                exec_s = lat - plan_s
            oh = wall - lat if wall > 0 else 0

            result = "PASS" if ok else "FAIL"
            print(
                f"{task_id:<14} {wall:>4.0f}s {plan_s:>5.0f}s  {exec_s:>5.0f}s "
                f"{calls:>4d}  {oh:>5.0f}s  {result}"
            )

            count += 1
            tw += wall
            tp += plan_s
            te += exec_s
            to += oh
            if ok:
                solved += 1

        print("-" * 75)
        print(
            f"{'TOTAL':<14} {tw:>4.0f}s {tp:>5.0f}s  {te:>5.0f}s        "
            f"{to:>5.0f}s  {solved}/{count} solved"
        )
        if count:
            sr = solved / count * 100
            print(f"  SR={sr:.0f}%  avg wall={tw/count:.0f}s  avg plan={tp/count:.0f}s  avg exec={te/count:.0f}s")

        # Errors for this config
        cfg_errors = error_by_config.get(config, [])
        if cfg_errors:
            deduped: dict[str, int] = {}
            for e in cfg_errors:
                short = re.sub(r"sess-\w+", "sess-XXX", e)
                deduped[short] = deduped.get(short, 0) + 1
            print(f"\n  Errors:")
            for msg, n in sorted(deduped.items(), key=lambda x: -x[1]):
                if "timeout" in msg.lower():
                    cause = "inference timeout (executor on large context)"
                elif "working memory" in msg.lower():
                    cause = "WM ceiling exceeded (retrieval inflates prompt)"
                else:
                    cause = "—"
                print(f"  [{n}x] {msg[:90]}")
                print(f"       -> {cause}")

    # Summary across all configs
    print(f"\n=== Cross-config Summary ===")
    for run in runs:
        config = run["config"]
        tasks = run["tasks"]
        pt = _per_task_results(config, run["dataset"])
        solved = sum(1 for tid, t in tasks.items() if pt.get(tid, {}).get("solved"))
        n = len(tasks)
        n_errors = len(error_by_config.get(config, []))
        print(f"  {config}: {solved}/{n} solved, {n_errors} warnings/errors")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <log_path>")
        sys.exit(1)
    diagnose(sys.argv[1])
