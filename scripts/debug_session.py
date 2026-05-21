"""Live debug-session smoke: one Aviona session, many prompts, debug log.

Usage:
    python scripts/debug_session.py [--workspace D:\\thesis\\aviona-test]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DebugCase:
    """One prompt and pass criteria for debug-session runs."""

    case_id: str
    prompt: str
    must_contain: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()
    max_steps: int = 6
    expected_files: dict[str, str] = field(default_factory=dict)
    cleanup_files: tuple[str, ...] = ()


DEBUG_MATRIX: tuple[DebugCase, ...] = (
    DebugCase("greeting-echo", 'just say "ali ali"', must_contain=("ali ali",), max_steps=1),
    DebugCase(
        "meta-model",
        "tell me what is your llm model?",
        must_contain=("deepseek",),
        max_steps=1,
    ),
    DebugCase("meta-gpt", "are you gpt?", must_contain=("deepseek",), max_steps=1),
    DebugCase("meta-hi", "hi", must_contain=("hi",), max_steps=1),
    DebugCase(
        "inspect-hello",
        "what is content of hello file?",
        must_contain=("hi",),
        max_steps=3,
    ),
    DebugCase(
        "inspect-list",
        "list files in this dir",
        must_contain=("hello.txt", "main.py"),
        max_steps=3,
    ),
    DebugCase(
        "inspect-explain",
        "read main.py and briefly explain what it does in one sentence",
        must_contain=("main",),
        max_steps=3,
    ),
    DebugCase(
        "inspect-empty",
        "what is the content of solution.py?",
        must_contain=("empty",),
        max_steps=3,
    ),
    DebugCase(
        "edit-bar",
        'create bar.txt with "debug-smoke"',
        must_contain=("bar.txt",),
        max_steps=6,
        expected_files={"bar.txt": "debug-smoke"},
        cleanup_files=("bar.txt",),
    ),
)


def _file_text(workspace: Path, rel: str) -> str:
    path = workspace / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def run_debug_session(*, workspace: Path) -> Path:
    """Run all prompts in one session; return debug log path."""
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "src"))

    from aviona.debug_log import close_debug_log, debug_log_path, enable_debug_log
    from aviona.env import load_aviona_env
    from aviona.session import AvionaSession
    from framework.orchestration.session import ensure_slm_api_key_configured

    load_aviona_env(workspace)
    ensure_slm_api_key_configured()

    session = AvionaSession(workspace)
    session.set_mode("auto")
    log_path = enable_debug_log(
        workspace=workspace,
        session_id=session._session_id,
    )

    provider = ""
    model = ""
    try:
        from aviona.runtime import runtime_anchor_segment

        seg = runtime_anchor_segment(cwd=workspace)
        pm = re.search(r"provider=([^|]+)", seg)
        mm = re.search(r"model=([^|]+)", seg)
        provider = (pm.group(1).strip() if pm else "")
        model = (mm.group(1).strip() if mm else "").split("/")[-1]
    except Exception:
        pass

    print(f"==> debug session workspace={workspace}")
    print(f"==> session_id={session._session_id}")
    print(f"==> log={log_path}")
    print(f"==> provider={provider!r} model={model!r}")
    print(f"==> cases={len(DEBUG_MATRIX)} (single session, sequential)")
    print()

    failures: list[str] = []

    for case in DEBUG_MATRIX:
        for rel in case.cleanup_files:
            target = workspace / rel
            if target.is_file():
                target.unlink()

        print(f"  -> [{case.case_id}] {case.prompt!r}")
        started = time.perf_counter()
        try:
            result = session.run_turn(case.prompt)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{case.case_id}: exception {exc}")
            print(f"     FAIL exception: {exc}")
            continue

        elapsed = time.perf_counter() - started
        detail = (result.detail or "").lower()
        status = result.status.lower()

        if result.outcome != "solved" or (result.detail or "").strip().startswith("!"):
            failures.append(
                f"{case.case_id}: outcome={result.outcome} detail={result.detail!r}"
            )
            print(f"     FAIL {result.status} detail={result.detail!r} ({elapsed:.1f}s)")
            continue

        if result.step_count > case.max_steps:
            failures.append(
                f"{case.case_id}: steps {result.step_count} > {case.max_steps}"
            )
            print(f"     FAIL budget {result.step_count} steps ({elapsed:.1f}s)")
            continue

        needles = list(case.must_contain)
        if case.case_id in ("meta-model", "meta-gpt") and model:
            needles.append(model)
        for needle in needles:
            if needle.lower() not in detail and needle.lower() not in status:
                failures.append(f"{case.case_id}: missing {needle!r} in {detail!r}")
                print(f"     FAIL missing {needle!r} ({elapsed:.1f}s)")
                break
        else:
            for needle in case.must_not_contain:
                if needle.lower() in detail:
                    failures.append(f"{case.case_id}: must not contain {needle!r}")
                    print(f"     FAIL forbidden {needle!r} ({elapsed:.1f}s)")
                    break
            else:
                for rel, expected in case.expected_files.items():
                    actual = _file_text(workspace, rel).strip()
                    if actual != expected.strip():
                        failures.append(
                            f"{case.case_id}: {rel} expected {expected!r}, got {actual!r}"
                        )
                        print(f"     FAIL file {rel} ({elapsed:.1f}s)")
                        break
                else:
                    print(
                        f"     ok | {result.step_count} steps | "
                        f"{result.tokens_total} tok | {elapsed:.1f}s"
                    )

    close_debug_log()
    print()
    if failures:
        print(f"==> DEBUG SESSION FAILED ({len(failures)} issues)")
        for line in failures:
            print(f"  - {line}")
        print(f"==> log: {log_path}")
        raise SystemExit(1)

    print(f"==> DEBUG SESSION PASSED ({len(DEBUG_MATRIX)} cases)")
    print(f"==> log: {log_path}")
    return log_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aviona multi-prompt debug session")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(r"D:\thesis\aviona-test"),
    )
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        print(f"error: workspace not found: {workspace}", file=sys.stderr)
        return 1
    try:
        run_debug_session(workspace=workspace)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
