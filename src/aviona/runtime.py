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
        "CURRENT user goal from the runtime: line in [CONSTRAINTS]. Ignore prior turns. "
        "Do not read repository files, handoff, or write tools. "
        "Use terminate{user_message, turn_type:answer} in one cycle."
    )


def interactive_turn_contract_hint() -> str:
    """Per-turn contract hint for all REPL goals (not meta-only)."""
    return (
        "[AVIONA] Turn types: short greetings (hi, hello, ok) → terminate turn_type:answer "
        "only — reply to the CURRENT goal, not prior turns; do not run project smoke examples. "
        "Identity/model questions → turn_type:answer from runtime: facts (1 cycle). "
        "Read/list/explain → list_dir/read_file tools then terminate turn_type:inspect (≤3 cycles). "
        "Run/execute code with input → shell (python) then terminate turn_type:inspect with stdout (≤6 cycles). "
        "Create/edit → code_edit with turn_type:edit then terminate turn_type:edit (≤6 cycles). "
        "Tools available: list_dir, read_file, code_edit, shell."
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


def infer_interactive_max_steps(goal: str) -> int:
    """Map user goal shape to the interactive executor cycle ceiling."""
    if is_answer_only_goal(goal):
        return 1
    lower = goal.strip().lower()
    if any(
        token in lower
        for token in (
            "run this",
            "run the",
            "run code",
            "execute",
            "with input",
            "show me the result",
        )
    ):
        return 6
    if any(
        token in lower
        for token in (
            "list",
            "read",
            "content",
            "explain",
            "what is",
            "show",
            "inspect",
            "directory",
            "files in",
        )
    ):
        return 3
    if any(
        token in lower
        for token in ("create", "edit", "write", "add ", "fix ", "update", "delete")
    ):
        return 6
    return 3
