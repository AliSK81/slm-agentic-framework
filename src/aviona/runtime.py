"""Runtime facts injected into the session anchor for every agent turn."""

from __future__ import annotations

from pathlib import Path


def runtime_anchor_segment(*, cwd: Path | None = None) -> str:
    """Provider, model, version, and cwd — agents answer self-questions from this block.

    Args:
        cwd: Optional workspace path included as a runtime fact (not repo file reads).

    Returns:
        One-line runtime segment for the rolling anchor block.
    """
    from aviona import __version__
    from framework.slm.config import active_provider_name, load_profile
    from framework.slm.registry import resolve_profile_name

    provider = active_provider_name()
    planner = load_profile(resolve_profile_name("planner"))
    executor = load_profile(resolve_profile_name("executor"))
    if planner.model_id == executor.model_id:
        models = planner.model_id
    else:
        models = f"planner={planner.model_id}, executor={executor.model_id}"
    parts = [
        "product=aviona",
        f"version={__version__}",
        f"provider={provider}",
        f"model={models}",
    ]
    if cwd is not None:
        parts.append(f"cwd={cwd.resolve()}")
    return "runtime: " + " | ".join(parts)


def runtime_answer_constraint() -> str:
    """Hard constraint instructing meta answers from the anchor runtime line."""
    return (
        "[AVIONA] Self/meta questions (model, provider, version, cwd): answer only the "
        "CURRENT user goal from the runtime: line in [CONSTRAINTS]. Ignore [CONTEXT] items "
        "— they may be stale from prior sessions. "
        "Do not read repository files, handoff, or write tools. "
        "Use terminate{user_message, turn_type:answer} in one cycle."
    )


def interactive_turn_contract_hint() -> str:
    """Per-turn contract hint for all REPL goals (not meta-only)."""
    return (
        "[AVIONA] Turn types: short greetings (hi, hello, ok) → terminate turn_type:answer "
        "only — reply to the CURRENT goal, not prior turns; do not run project smoke examples. "
        "Identity/model questions → turn_type:answer from runtime: facts (1 cycle). "
        "Read/list/explain → read_file/list_dir/glob then terminate turn_type:inspect (≤3 cycles). "
        "Explore/search (e.g. md files) → glob or read_file on matches, not bare list_dir. "
        "Run/execute code or pytest → shell then terminate turn_type:inspect with stdout (≤6 cycles). "
        "Create/edit/write tests → code_edit turn_type:edit then terminate turn_type:edit (≤6 cycles). "
        "Tools available: list_dir, read_file, glob, code_edit, pytest, shell."
    )


_META_QUESTION_MARKERS: tuple[str, ...] = (
    "your model",
    "llm model",
    "language model",
    "what model",
    "which model",
    "are you gpt",
    "are you claude",
    "who are you",
    "what are you",
    "what provider",
    "aviona version",
    "what version",
)


def is_meta_question(goal: str) -> bool:
    """True when the user goal is about Aviona/runtime identity (not repo content)."""
    lower = goal.strip().lower()
    return any(marker in lower for marker in _META_QUESTION_MARKERS)


def is_answer_only_goal(goal: str) -> bool:
    """True when the turn must be a single-cycle answer (greeting or meta)."""
    normalized = goal.strip().lower().strip('"').strip("'")
    if normalized in ("hi", "hello", "hey", "ok", "thanks", "thank you", "salam"):
        return True
    return is_meta_question(goal)
