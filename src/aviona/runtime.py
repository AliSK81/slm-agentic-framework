"""Runtime facts injected into the session anchor for every agent turn."""


def runtime_anchor_segment() -> str:
    """Provider and model identity — agents answer from this, not repo files.

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
    return f"runtime: aviona {__version__} | provider {provider} | model {models}"
