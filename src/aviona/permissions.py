"""Aviona permission modes layered on the framework sandbox (never widens it)."""

from __future__ import annotations

import logging
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from framework.error_control.sandbox import SAFE_COMMANDS, _command_allowed

logger = logging.getLogger(__name__)

Mode = Literal["plan", "default", "auto"]
PermissionVerdict = Literal["allow", "ask", "deny"]
ActionKind = Literal["write_file", "edit_file", "shell"]

READ_ONLY_SHELL: frozenset[str] = frozenset({"cat", "ls", "find", "diff", "echo", "ast"})


class PermissionAction(BaseModel):
    """A gated file or shell operation."""

    kind: ActionKind
    detail: str = ""


class PermissionGate:
    """Per-session permission layer for Aviona tool and shell actions."""

    def __init__(
        self,
        mode: Mode = "default",
        *,
        allowlist: list[str] | None = None,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        self.mode = mode
        self.allowlist = list(allowlist or [])
        self._confirm = confirm or (lambda _prompt: False)

    def set_mode(self, mode: Mode) -> None:
        """Switch the active permission mode."""
        self.mode = mode

    def set_confirm(self, confirm: Callable[[str], bool]) -> None:
        """Install a confirmation callback (REPL injects ``reader`` here)."""
        self._confirm = confirm

    def check(self, action: PermissionAction) -> PermissionVerdict:
        """Return ``allow``, ``ask``, or ``deny`` without invoking confirm."""
        if action.kind in ("write_file", "edit_file"):
            if self.mode == "plan":
                return "deny"
            return "allow"

        if action.kind == "shell":
            cmd = action.detail.strip()
            if not cmd:
                return "deny"
            if not self._shell_framework_allowed(cmd):
                return "deny"
            if not self._shell_project_allowed(cmd):
                return "deny"
            if self.mode == "plan" and self._shell_is_side_effecting(cmd):
                return "deny"
            if self.mode == "default" and self._shell_is_side_effecting(cmd):
                return "ask"
            return "allow"

        return "deny"

    def ensure(self, action: PermissionAction) -> bool:
        """Return True when the action may proceed (runs confirm on ``ask``)."""
        verdict = self.check(action)
        if verdict == "allow":
            return True
        if verdict == "deny":
            logger.info("Permission denied: %s %s", action.kind, action.detail)
            return False
        prompt = f"Allow {action.kind} {action.detail}? [y/N] "
        return self._confirm(prompt)

    @staticmethod
    def _shell_framework_allowed(cmd: str) -> bool:
        """Command must pass the framework ``SAFE_COMMANDS`` gate (never widened)."""
        return _command_allowed(cmd)

    def _shell_project_allowed(self, cmd: str) -> bool:
        """When a project allowlist is configured, command must match an entry."""
        if not self.allowlist:
            return True
        normalized = cmd.strip()
        first = _executable_name(normalized)
        for entry in self.allowlist:
            entry = entry.strip()
            if not entry:
                continue
            if normalized == entry or normalized.startswith(entry + " "):
                return True
            if _executable_name(entry) == first and entry in normalized:
                return True
            if first == _executable_name(entry):
                return True
        return False

    @staticmethod
    def _shell_is_side_effecting(cmd: str) -> bool:
        name = _executable_name(cmd)
        return name not in READ_ONLY_SHELL


def _executable_name(cmd: str) -> str:
    parts = shlex.split(cmd, posix=False)
    if not parts:
        return ""
    raw = parts[0].replace('"', "").replace("'", "")
    name = Path(raw).name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def merged_safe_commands(project_allowlist: list[str]) -> frozenset[str]:
    """Return project commands that are also in ``SAFE_COMMANDS`` (subset only)."""
    allowed: set[str] = set()
    for entry in project_allowlist:
        name = _executable_name(entry)
        if name in SAFE_COMMANDS:
            allowed.add(name)
    return frozenset(allowed)
