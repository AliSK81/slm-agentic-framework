"""Skill card loader for Working Memory guidance."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


class SkillCard(BaseModel):
    """YAML skill card for prompt guidance."""

    name: str
    trigger_keywords: list[str] = Field(default_factory=list)
    content: str


def load_skill_cards(skills_dir: Path | None = None) -> list[SkillCard]:
    """Load all skill card YAML files from the skills directory."""
    directory = skills_dir or _SKILLS_DIR
    cards: list[SkillCard] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cards.append(SkillCard.model_validate(raw))
    return cards


def select_skill_card(
    *,
    agent_role: str,
    last_error: str | None,
    current_subtask: str,
    cards: list[SkillCard] | None = None,
) -> str | None:
    """Select skill card: error_recovery > recency > intent keyword match."""
    all_cards = cards if cards is not None else load_skill_cards()
    role_prefix = "planner" if agent_role == "planner" else "executor"
    role_cards = [c for c in all_cards if c.name.startswith(role_prefix)]

    if last_error:
        error_lower = last_error.lower()
        for card in role_cards:
            if any(kw.lower() in error_lower for kw in card.trigger_keywords):
                return card.content

    subtask_lower = current_subtask.lower()
    for card in role_cards:
        if any(kw.lower() in subtask_lower for kw in card.trigger_keywords):
            return card.content

    return None
