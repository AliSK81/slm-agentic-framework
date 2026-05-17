"""Timeout wrapper for blocking calls."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TimeoutResult(BaseModel):
    """Returned when a watched call exceeds its timeout."""

    timed_out: bool = True
    error: str = "timeout"


def call_with_timeout(
    fn: Callable[..., T],
    args: dict[str, Any],
    timeout_s: int,
) -> T | TimeoutResult:
    """Run fn in a thread pool; return TimeoutResult on timeout (never raises)."""
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, **args)
            return future.result(timeout=timeout_s)
    except FuturesTimeoutError:
        logger.warning("call_with_timeout exceeded %ss", timeout_s)
        return TimeoutResult()
    except Exception as exc:  # noqa: BLE001 — watchdog must not raise
        logger.warning("call_with_timeout failed: %s", exc)
        return TimeoutResult(timed_out=False, error=str(exc))
