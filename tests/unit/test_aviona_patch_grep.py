"""Grep gate: patch-stack symbols must not remain in src/aviona/."""

from __future__ import annotations

from pathlib import Path


def test_no_patch_stack_symbols_in_aviona_src() -> None:
    """V2-4 deletion gate — banned symbols absent from product source."""
    root = Path(__file__).resolve().parents[2] / "src" / "aviona"
    banned = (
        "classify_goal",
        "analyze_turn_effects",
        "try_read_content_fallback",
        "try_explain_fallback",
        "_AVIONA_",
        "_REVERT_ON_FAILURE",
        "_best_answer",
    )
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == []
