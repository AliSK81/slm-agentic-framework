"""Aviona console entry point (package script ``aviona``)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from aviona import __version__
from aviona.doctor import run_doctor
from aviona.env import load_aviona_env
from aviona.repl import run_repl
from aviona.session import AvionaSession
from framework.orchestration.session import validate_slm_api_key


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``aviona`` argument parser.

    Returns:
        Configured ``ArgumentParser`` with ``--version``, ``doctor``, and default REPL stub.
    """
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
        "--mode",
        choices=["plan", "default", "auto"],
        default=None,
        help="Permission mode: plan (read-only), default (ask shell), auto.",
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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Aviona CLI.

    Loads ``~/.aviona/.env`` then project ``.env`` (secrets never echoed). Bare ``aviona``
    probes once then starts the REPL; ``doctor`` probes only; ``undo`` restores snapshots.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
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
            print("nothing to undo")
            return 0
        print("restored:", ", ".join(restored))
        return 0

    validate_slm_api_key()
    session = AvionaSession(cwd)
    if getattr(args, "mode", None):
        session.set_mode(args.mode)  # type: ignore[arg-type]
    return run_repl(session)


if __name__ == "__main__":
    sys.exit(main())
