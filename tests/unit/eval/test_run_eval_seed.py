"""Unit tests for run_eval seed handling (multi-seed ablations)."""

from __future__ import annotations

from unittest.mock import patch

from eval.run_eval import run_eval


def test_run_eval_cli_seed_overrides_dataset_yaml() -> None:
    """``--seed`` from ablation/CLI is used for sampling, not eval.yaml dataset default."""
    seen: list[int] = []

    def _fake_curated(*, n: int, seed: int, ids_file: str | None = None) -> list:
        _ = n, ids_file
        seen.append(seed)
        return []

    with patch(
        "eval.run_eval.load_humaneval_curated_hard",
        side_effect=_fake_curated,
    ):
        run_eval("A", "discriminative", n=5, seed=41, dry_run=True)
        run_eval("A", "discriminative", n=5, seed=43, dry_run=True)

    assert seen == [41, 43]
