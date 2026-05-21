"""Structural tests for scripts/live_gate.py L3 matrix (no API)."""

from __future__ import annotations

import runpy
from pathlib import Path


def _live_globals() -> dict:
    repo = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(repo / "scripts" / "live_gate.py"))


def test_live_matrix_has_expanded_session_rows() -> None:
    """AV3-3 matrix includes the real-session failure-mode rows."""
    g = _live_globals()
    matrix = g["LIVE_MATRIX"]
    ids = {c.case_id for c in matrix}
    required = {
        "inspect-main-file",
        "inspect-explore-md",
        "inspect-partial",
        "inspect-empty",
        "run-input",
        "edit-test-run",
        "anaphora-read",
        "repeat-list",
    }
    assert required <= ids
    assert len(matrix) >= 16


def test_live_matrix_case_ids_unique() -> None:
    """Every live case id appears once."""
    matrix = _live_globals()["LIVE_MATRIX"]
    ids = [c.case_id for c in matrix]
    assert len(ids) == len(set(ids))


def test_live_matrix_budgets_use_framework_caps() -> None:
    """Inspect/edit rows use FI-1 budgets from configs/models.yaml."""
    g = _live_globals()
    assert g["_budget"]("inspect") == 4
    assert g["_budget"]("edit") == 6
    for case in g["LIVE_MATRIX"]:
        if case.max_steps is not None and case.turn_type == "inspect":
            assert case.max_steps <= 4 + g["_budget"]("run")
