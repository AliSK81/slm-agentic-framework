"""Phase 0 smoke tests — project skeleton collects and imports."""

def test_python_environment_when_bootstrap_complete_then_imports_succeed() -> None:
    """Verify core dependencies are importable after bootstrap."""
    import langgraph  # noqa: F401
    import pydantic  # noqa: F401
    import redis  # noqa: F401
    from dotenv import load_dotenv  # noqa: F401

    assert True
