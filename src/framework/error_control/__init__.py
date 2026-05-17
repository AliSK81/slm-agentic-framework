"""Error control infrastructure — deterministic wrappers around LLM/tool I/O."""

from framework.error_control.parser import parse_decision
from framework.error_control.quality import QualityGate, QualityResult
from framework.error_control.sandbox import SAFE_COMMANDS, SubprocessResult, safe_execute
from framework.error_control.thinking import ThinkingBudget
from framework.error_control.truncation import CAPS, truncate
from framework.error_control.watchdog import TimeoutResult, call_with_timeout

__all__ = [
    "CAPS",
    "SAFE_COMMANDS",
    "QualityGate",
    "QualityResult",
    "SubprocessResult",
    "ThinkingBudget",
    "TimeoutResult",
    "call_with_timeout",
    "parse_decision",
    "safe_execute",
    "truncate",
]
