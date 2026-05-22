"""Ablation feature toggles for Decision Cycle and session runs."""

from __future__ import annotations

from pydantic import BaseModel


class AblationSettings(BaseModel):
    """Feature toggles for configs A–D (memory, control, error control)."""

    memory: bool = True
    control: bool = True
    error_control: bool = True
    wm_ceiling_override: int | None = None
