"""Aviona ``--debug`` file logging (Claude Code style)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DEBUG_LOGGER = "aviona.debug.file"
_ATTACHED_LOGGERS = ("aviona", "framework")
_handler: logging.FileHandler | None = None
_log_path: Path | None = None
_prior_levels: dict[str, int] = {}


class _DebugFileFormatter(logging.Formatter):
    """ISO-8601 UTC lines: ``2026-05-21T08:40:06.024Z [DEBUG] message``."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"
        return f"{ts} [{record.levelname}] {record.getMessage()}"


def debug_log_dir() -> Path:
    """Return ``~/.aviona/debug/`` (created on demand)."""
    return Path.home() / ".aviona" / "debug"


def debug_log_path() -> Path | None:
    """Active debug log path when ``--debug`` is enabled."""
    return _log_path


def is_debug_enabled() -> bool:
    """True when a debug log file is attached to this process."""
    return _log_path is not None


def enable_debug_log(*, workspace: Path, session_id: str) -> Path:
    """Attach a per-run debug log file; return its path.

    Args:
        workspace: REPL cwd.
        session_id: Aviona session id for correlation in log lines.

    Returns:
        Absolute path to the new ``.txt`` log file.
    """
    global _handler, _log_path, _prior_levels

    if _handler is not None:
        close_debug_log()

    debug_log_dir().mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    path = debug_log_dir() / f"{run_id}.txt"
    _log_path = path

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_DebugFileFormatter())
    handler.setLevel(logging.DEBUG)
    setattr(handler, "_aviona_debug_handler", True)
    _handler = handler

    file_logger = logging.getLogger(_DEBUG_LOGGER)
    file_logger.handlers.clear()
    file_logger.setLevel(logging.DEBUG)
    file_logger.propagate = False
    file_logger.addHandler(handler)

    _prior_levels.clear()
    for name in _ATTACHED_LOGGERS:
        target = logging.getLogger(name)
        _prior_levels[name] = target.level
        target.setLevel(logging.DEBUG)
        target.addHandler(handler)

    from aviona import __version__
    from aviona.runtime import runtime_anchor_segment

    log_event(
        f"[STARTUP] debug enabled run_id={run_id} session_id={session_id} "
        f"workspace={workspace.resolve()} version={__version__}"
    )
    log_event(f"[STARTUP] {runtime_anchor_segment(cwd=workspace)}")
    return path


def log_event(message: str, *, level: int = logging.DEBUG) -> None:
    """Write one structured line to the debug log (no-op when disabled)."""
    if _log_path is None:
        return
    logging.getLogger(_DEBUG_LOGGER).log(level, message)


def log_repl_user(text: str) -> None:
    """Record a user REPL line."""
    log_event(f"[REPL] user input: {text!r}")


def log_turn_start(*, goal: str, session_id: str) -> None:
    """Record the start of one agent turn."""
    log_event(f"[REPL] turn start goal={goal!r} session_id={session_id}")


def log_turn_summary(
    *,
    goal: str,
    status: str,
    detail: str | None,
    step_count: int,
    tokens_total: int,
    outcome: str,
    elapsed_ms: int,
    turn_type: str = "",
    contract_passed: bool = True,
    failure_reason: str | None = None,
    decision_rows: list[tuple[str, dict]],
) -> None:
    """Record one completed turn with decision-log snapshot."""
    log_event(
        f"[REPL] turn done goal={goal!r} outcome={outcome} turn_type={turn_type!r} "
        f"contract_passed={contract_passed} steps={step_count} tokens={tokens_total} "
        f"elapsed_ms={elapsed_ms} status={status!r}"
    )
    if failure_reason:
        log_event(f"[REPL] contract_fail: {failure_reason!r}")
    if detail:
        log_event(f"[REPL] user_message: {detail!r}")
    for kind, payload in decision_rows:
        payload_text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(payload_text) > 500:
            payload_text = payload_text[:500] + "...(truncated)"
        log_event(f"[DECISION] kind={kind} payload={payload_text}")


def close_debug_log() -> None:
    """Detach debug handlers and restore prior logger levels."""
    global _handler, _log_path, _prior_levels

    if _handler is None:
        return

    log_event("[SHUTDOWN] debug session ended")

    for name in _ATTACHED_LOGGERS:
        target = logging.getLogger(name)
        target.removeHandler(_handler)
        if name in _prior_levels:
            target.setLevel(_prior_levels[name])

    file_logger = logging.getLogger(_DEBUG_LOGGER)
    file_logger.handlers.clear()
    _handler.close()
    _handler = None
    _log_path = None
    _prior_levels.clear()
