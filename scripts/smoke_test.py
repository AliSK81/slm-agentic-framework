#!/usr/bin/env python3
"""Smoke test: run TASK_1 end-to-end and print outcome."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from framework.orchestration.session import run_full_session  # noqa: E402

TASK_1 = {
    "goal": "Write a Python function add(a, b) that returns a + b.",
    "constraints": ["Must be named exactly 'add'", "Must handle integers and floats"],
    "test_code": "assert add(1, 2) == 3\nassert add(1.5, 2.5) == 4.0",
}


def main() -> int:
    workspace = _PROJECT_ROOT / "workspace" / "smoke"
    workspace.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = _PROJECT_ROOT / "checkpoints"

    try:
        result = run_full_session(
            TASK_1["goal"],
            TASK_1["constraints"],
            TASK_1["test_code"],
            workspace,
            max_steps=12,
            checkpoint_dir=checkpoint_dir,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    decisions = result.decision_count
    print(f"Session: {result.session_id}")
    print(f"Decisions logged: {decisions}")
    print(f"Test passed: {result.test_passed}")
    print(f"OUTCOME: {result.outcome}")
    return 0 if result.outcome == "solved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
