"""Aviona console entry point (package script ``aviona``)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from aviona import __version__
from aviona.console import configure_stdio, write_line
from aviona.doctor import run_doctor
from aviona.env import load_aviona_env
from aviona.repl import run_repl
from aviona.session import AvionaSession
from aviona.store import SessionNotFoundError, latest_session
from framework.orchestration.session import ensure_slm_api_key_configured


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``aviona`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="aviona",
        description="Terminal agent for project-local file edits (thesis framework).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write verbose debug log to ~/.aviona/debug/<run-id>.txt",
    )
    parser.add_argument(
        "--mode",
        choices=["plan", "default", "auto"],
        default=None,
        help="Permission mode: plan (read-only), default (ask shell), auto.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Non-interactive: permission mode auto (no shell confirm prompts).",
    )
    parser.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="Resume the latest session for this project.",
    )
    parser.add_argument(
        "--resume",
        metavar="SESSION_ID",
        default=None,
        help="Resume a specific session id.",
    )
    parser.add_argument(
        "--fork-session",
        action="store_true",
        help="Start a new session linked to --resume id or the latest session.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "doctor",
        help="Probe SLM connectivity (no session, no REPL).",
    )
    subparsers.add_parser(
        "undo",
        help="Restore files snapshotted before the last turn's edits.",
    )
    return parser


def _open_session(cwd: Path, args: argparse.Namespace) -> AvionaSession | None:
    """Create or resume an ``AvionaSession`` from CLI flags."""
    if args.fork_session:
        parent_id = args.resume
        if parent_id is None:
            latest = latest_session(cwd)
            if latest is None:
                write_line("no prior session to fork")
                return None
            parent_id = latest.session_id
        try:
            return AvionaSession(cwd, fork_from=parent_id)
        except SessionNotFoundError as exc:
            write_line(str(exc))
            return None

    if args.continue_session:
        latest = latest_session(cwd)
        if latest is None:
            write_line("no prior session to continue")
            return None
        return AvionaSession(cwd, session_id=latest.session_id)

    if args.resume:
        try:
            return AvionaSession(cwd, session_id=args.resume)
        except SessionNotFoundError as exc:
            write_line(str(exc))
            return None

    return AvionaSession(cwd)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Aviona CLI."""
    configure_stdio()
    cwd = Path.cwd()
    load_aviona_env(cwd)
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 0

    if args.command == "doctor":
        return run_doctor()

    if args.command == "undo":
        session = AvionaSession(cwd)
        restored = session.undo_last()
        if not restored:
            write_line("nothing to undo")
            return 0
        write_line("restored: " + ", ".join(restored))
        return 0

    ensure_slm_api_key_configured()
    session = _open_session(cwd, args)
    if session is None:
        return 1
    if getattr(args, "yes", False) or not sys.stdin.isatty():
        session.set_mode("auto")
    elif getattr(args, "mode", None):
        session.set_mode(args.mode)  # type: ignore[arg-type]
    return run_repl(session, debug=bool(getattr(args, "debug", False)))


if __name__ == "__main__":
    sys.exit(main())
