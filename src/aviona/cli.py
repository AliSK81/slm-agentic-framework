"""Aviona console entry point (package script ``aviona``)."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from pathlib import Path

from aviona import __version__
from aviona.repl import run_repl
from aviona.session import AvionaSession
from framework.env import load_project_env
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
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "doctor",
        help="Check environment and API connectivity (stub in AVIONA-1).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Aviona CLI.

    Loads project ``.env`` via ``load_project_env`` (no secret I/O). Bare ``aviona`` probes the
    SLM once, then starts the interactive REPL; ``doctor`` is a stub until later phases.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    load_project_env()
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 0

    if args.command == "doctor":
        print("aviona doctor: not implemented yet (AVIONA-1 stub).")
        return 0

    validate_slm_api_key()
    session = AvionaSession(Path.cwd())
    return run_repl(session)


if __name__ == "__main__":
    sys.exit(main())
