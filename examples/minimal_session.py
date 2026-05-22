"""Run a minimal full session on a simple coding task."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from framework.env import load_project_env  # noqa: E402
from framework.orchestration.session import run_full_session  # noqa: E402


def main() -> int:
    """Execute a tiny end-to-end task using configured SLM provider settings."""
    load_project_env()
    workspace = PROJECT_ROOT / "workspace" / "example-minimal"
    workspace.mkdir(parents=True, exist_ok=True)

    result = run_full_session(
        "Write a Python function add(a, b) that returns a + b.",
        ["Must be named exactly 'add'", "Must handle integers and floats"],
        "assert add(1, 2) == 3\nassert add(1.5, 2.5) == 4.0",
        workspace,
        max_steps=12,
        checkpoint_dir=PROJECT_ROOT / "checkpoints",
    )
    print(f"Outcome: {result.outcome}")
    print(f"Test passed: {result.test_passed}")
    return 0 if result.outcome == "solved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
