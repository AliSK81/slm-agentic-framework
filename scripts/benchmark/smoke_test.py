#!/usr/bin/env python3
"""Smoke test: run TASK_1 end-to-end and print outcome."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from framework.env import load_project_env  # noqa: E402
from framework.orchestration.session import run_full_session  # noqa: E402
from framework.slm.config import resolve_bundle  # noqa: E402

TASK_1 = {
    "goal": "Write a Python function add(a, b) that returns a + b.",
    "constraints": ["Must be named exactly 'add'", "Must handle integers and floats"],
    "test_code": "assert add(1, 2) == 3\nassert add(1.5, 2.5) == 4.0",
}


def _apply_bundle(bundle_name: str) -> None:
    """Set role profile env vars and provider for a named models.yaml bundle."""
    from framework.slm.config import _load_raw, clear_config_cache

    profiles = resolve_bundle(bundle_name)
    os.environ["PLANNER_PROFILE"] = profiles["planner"]
    os.environ["EXECUTOR_PROFILE"] = profiles["executor"]
    block = _load_raw().get("bundles", {}).get(bundle_name, {})
    provider = str(block.get("provider", "openrouter")).strip()
    if provider:
        os.environ["SLM_PROVIDER"] = provider
    clear_config_cache()


def main(argv: list[str] | None = None) -> int:
    """Run TASK_1 smoke session; optional ``--bundle slm_small`` for true-SLM path."""
    parser = argparse.ArgumentParser(description="End-to-end smoke test (TASK_1)")
    parser.add_argument(
        "--bundle",
        default=None,
        help="Named profile bundle from configs/models.yaml (e.g. slm_small)",
    )
    args = parser.parse_args(argv)

    load_project_env()
    if args.bundle:
        _apply_bundle(args.bundle)

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
    if args.bundle:
        print(f"Bundle: {args.bundle}")
    print(f"Decisions logged: {decisions}")
    print(f"Test passed: {result.test_passed}")
    print(f"OUTCOME: {result.outcome}")
    return 0 if result.outcome == "solved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
