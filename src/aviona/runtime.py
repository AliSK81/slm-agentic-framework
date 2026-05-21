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
        "[AVIONA] Self/meta questions (model, provider, version, cwd): answer only from "
        "the runtime: line already in [CONSTRAINTS]. Do not read repository files, "
        "handoff, or write tools. Use terminate{user_message, turn_type:answer} in one cycle."
    )
