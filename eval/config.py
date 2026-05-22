"""Load evaluation configuration from configs/eval.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class StepBudget(BaseModel):
    """Per-dataset step and retry limits."""

    max_steps: int = 10
    max_retries: int = 3


class AblationFlags(BaseModel):
    """Feature toggles for ablation configs A–D."""

    memory: bool = False
    control: bool = False
    error_control: bool = False
    wm_ceiling_override: int | None = None


class EvalConfig(BaseModel):
    """Parsed configs/eval.yaml."""

    humaneval: dict[str, Any] = Field(default_factory=dict)
    humaneval_hard: dict[str, Any] = Field(default_factory=dict)
    discriminative: dict[str, Any] = Field(default_factory=dict)
    multistep: dict[str, Any] = Field(default_factory=dict)
    mbpp: dict[str, Any] = Field(default_factory=dict)
    swebench: dict[str, Any] = Field(default_factory=dict)
    step_budgets: dict[str, StepBudget] = Field(default_factory=dict)
    ablation_configs: dict[str, AblationFlags] = Field(default_factory=dict)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_eval_config(path: Path | None = None) -> EvalConfig:
    """Load and validate evaluation YAML."""
    runtime_path = _project_root() / "configs" / "runtime" / "eval.yaml"
    legacy_path = _project_root() / "configs" / "eval.yaml"
    config_path = path or (runtime_path if runtime_path.is_file() else legacy_path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    budgets: dict[str, StepBudget] = {}
    for name, values in (raw.get("step_budgets") or {}).items():
        budgets[name] = StepBudget.model_validate(values)
    ablations: dict[str, AblationFlags] = {}
    for name, values in (raw.get("ablation_configs") or {}).items():
        ablations[name] = AblationFlags.model_validate(values)
    return EvalConfig(
        humaneval=raw.get("humaneval") or {},
        humaneval_hard=raw.get("humaneval_hard") or {},
        discriminative=raw.get("discriminative") or {},
        multistep=raw.get("multistep") or {},
        mbpp=raw.get("mbpp") or {},
        swebench=raw.get("swebench") or {},
        step_budgets=budgets,
        ablation_configs=ablations,
    )
