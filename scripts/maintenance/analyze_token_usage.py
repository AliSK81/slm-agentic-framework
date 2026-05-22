#!/usr/bin/env python3
"""Estimate token usage from session SQLite DBs (API usage not persisted)."""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

from framework.control.cycle import _json_format_block
from framework.memory.stores import MemoryStores
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.runtime_dirs import traces_dir
from framework.slm.registry import client_for_role


def _decisions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT payload FROM memory_rows WHERE store = 'decisions' ORDER BY id"
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def _session_id(conn: sqlite3.Connection) -> str | None:
    rows = conn.execute(
        "SELECT payload FROM memory_rows WHERE store = 'subtasks' ORDER BY id"
    ).fetchall()
    for raw in rows:
        sub = json.loads(raw[0])
        tid = str(sub.get("task_id", ""))
        if tid.startswith("root:"):
            return sub.get("parent_session_id")
    return None


def analyze_db(db_path: Path) -> dict:
    memory = MemoryStores.sqlite(db_path)
    conn = sqlite3.connect(db_path)
    session_id = _session_id(conn)
    decisions = _decisions(conn)
    conn.close()
    if not session_id:
        return {"db": db_path.name, "error": "no session"}

    planner = client_for_role("planner")
    executor = client_for_role("executor")
    executor_wm = WorkingMemoryBuilder(memory, executor.profile)

    goal, _constraints = memory.subtasks.get_session_anchor(session_id)
    planner_wm = WorkingMemoryBuilder(memory, planner.profile).build(
        session_id=session_id,
        agent_role="planner",
        current_subtask=goal,
        subtask_id=f"root:{session_id}",
    )
    planner_block = planner_wm.to_prompt_prefix() + _json_format_block("planner")
    planner_prompt = max(len(planner_block) // 4, planner_wm.token_count())
    planner_calls = 1

    executor_prompt = 0
    executor_calls = 0

    for d in decisions:
        role = d.get("by_agent", "executor")
        sub_id = d.get("payload", {}).get("subtask_id") or f"root:{session_id}"
        desc = d.get("payload", {}).get("description", d.get("payload", {}).get("subtask", ""))
        if not desc:
            rows = memory.backend.query("subtasks", {"parent_session_id": session_id})
            work = [r for r in rows if not str(r.get("task_id", "")).startswith("root:")]
            desc = work[0].get("description", "implement solution") if work else "implement solution"
        builder = executor_wm
        wm = builder.build(
            session_id=session_id,
            agent_role=role,
            current_subtask=str(desc)[:2000],
            subtask_id=str(sub_id),
        )
        prompt = wm.to_prompt_prefix() + _json_format_block(role)
        tokens = max(len(prompt) // 4, wm.token_count())
        executor_prompt += tokens
        executor_calls += 1

    response_est = sum(max(len(json.dumps(d.get("payload", {}))) // 4, 80) for d in decisions)
    response_est += max(len(goal) // 8, 120)
    prompt_total = planner_prompt + executor_prompt

    return {
        "db": db_path.name,
        "decisions": len(decisions),
        "planner_calls": planner_calls,
        "executor_calls": executor_calls,
        "prompt_tokens_est": prompt_total,
        "response_tokens_est": response_est,
        "total_tokens_est": prompt_total + response_est,
    }


def main() -> int:
    data_dir = traces_dir() / "workspaces" / "D" / "humaneval" / "data"
    dbs = sorted(data_dir.glob("sess-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    dbs = dbs[:n]
    rows = [analyze_db(p) for p in dbs]
    rows = [r for r in rows if "error" not in r]
    for r in rows:
        print(r)
    if rows:
        avg = statistics.mean(r["total_tokens_est"] for r in rows)
        print(f"\nAverage estimated tokens per test (n={len(rows)}): {avg:.0f}")
        print("(Prompt WM reconstruction + rough response size; not OpenRouter billing.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
