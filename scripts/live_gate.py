"""L3 live acceptance gate for Aviona (ROADMAP_PRODUCTION_AVIONA_V2.md §6).

Invoked by ``scripts/test-aviona.ps1 -Live``. Requires a configured SLM API key.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class LiveCase:
    """One release-blocking live prompt and its invariants."""

    case_id: str
    prompt: str
    turn_type: str
    must_contain: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()
    max_steps: int | None = None
    unchanged_files: tuple[str, ...] = ()
    expected_files: dict[str, str] = field(default_factory=dict)
    cleanup_files: tuple[str, ...] = ()


LIVE_MATRIX: tuple[LiveCase, ...] = (
    LiveCase(
        "answer-hi",
        "hi",
        "answer",
        must_contain=("hi",),
        max_steps=1,
    ),
    LiveCase(
        "answer-ok",
        "ok",
        "answer",
        max_steps=1,
        unchanged_files=("notes.txt",),
    ),
    LiveCase(
        "answer-model",
        "what is your model?",
        "answer",
        max_steps=1,
    ),
    LiveCase(
        "answer-language-model",
        "what language model?",
        "answer",
        max_steps=1,
    ),
    LiveCase(
        "answer-salam",
        'try to fastly reply with "salam"',
        "answer",
        must_contain=("salam",),
        max_steps=1,
    ),
    LiveCase(
        "inspect-hello-content",
        "what is content of hello file?",
        "inspect",
        must_contain=("hi",),
        max_steps=3,
    ),
    LiveCase(
        "inspect-project",
        "what is this project",
        "inspect",
        must_contain=("Aviona test workspace",),
        max_steps=3,
    ),
    LiveCase(
        "inspect-list-files",
        "list files in this dir",
        "inspect",
        must_contain=("hello.txt", "main.py"),
        max_steps=3,
    ),
    LiveCase(
        "edit-create-foo",
        'create foo.txt with "x"',
        "edit",
        must_contain=("foo.txt",),
        max_steps=6,
        expected_files={"foo.txt": "x"},
        cleanup_files=("foo.txt",),
    ),
)


def _parse_runtime_facts(cwd: Path) -> tuple[str, str]:
    """Return provider and model substrings from the runtime anchor segment."""
    from aviona.runtime import runtime_anchor_segment

    segment = runtime_anchor_segment(cwd=cwd)
    provider_match = re.search(r"provider=([^|]+)", segment)
    model_match = re.search(r"model=([^|]+)", segment)
    provider = provider_match.group(1).strip() if provider_match else ""
    model = model_match.group(1).strip() if model_match else ""
    return provider, model


def _parse_step_count(output: str) -> int | None:
    """Return the last ``N steps`` count from REPL status lines."""
    matches = re.findall(r"\|\s*(\d+)\s+steps", output)
    return int(matches[-1]) if matches else None


def _run_repl_prompt(prompt: str, *, cwd: Path, aviona_exe: Path, timeout: int) -> str:
    """Pipe one prompt and ``/exit`` through the Aviona REPL."""
    proc = subprocess.run(
        [str(aviona_exe), "--mode", "auto"],
        input=f"{prompt}\n/exit\n",
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"aviona exited {proc.returncode} for prompt {prompt!r}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout + proc.stderr


def _file_text(workspace: Path, rel_path: str) -> str:
    path = workspace / rel_path
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _resolve_must_contain(case: LiveCase, *, provider: str, model: str) -> tuple[str, ...]:
    extra: list[str] = list(case.must_contain)
    if case.case_id == "answer-model":
        if provider:
            extra.append(provider)
        if model:
            extra.append(model.split("/")[-1] if "/" in model else model)
    if case.case_id == "answer-language-model" and model:
        token = model.split("/")[-1] if "/" in model else model
        extra.append(token)
    return tuple(extra)


def _check_case(
    case: LiveCase,
    *,
    workspace: Path,
    aviona_exe: Path,
    provider: str,
    model: str,
    timeout: int,
) -> None:
    """Run one live matrix row; raise AssertionError on failure."""
    snapshots = {rel: _file_text(workspace, rel) for rel in case.unchanged_files}
    for rel in case.cleanup_files:
        target = workspace / rel
        if target.is_file():
            target.unlink()

    output = _run_repl_prompt(case.prompt, cwd=workspace, aviona_exe=aviona_exe, timeout=timeout)

    if re.search(r"^\s*!\s", output, re.MULTILINE) or "no further action" in output.lower():
        raise AssertionError(f"{case.case_id}: failure or vacuous answer\n{output}")

    must_contain = _resolve_must_contain(case, provider=provider, model=model)
    for needle in must_contain:
        if needle.lower() not in output.lower():
            raise AssertionError(
                f"{case.case_id}: output missing {needle!r}\n{output}"
            )

    for needle in case.must_not_contain:
        if needle.lower() in output.lower():
            raise AssertionError(
                f"{case.case_id}: output must not contain {needle!r}\n{output}"
            )

    steps = _parse_step_count(output)
    if case.max_steps is not None:
        if steps is None:
            raise AssertionError(
                f"{case.case_id}: expected agent status with step count\n{output}"
            )
        if steps > case.max_steps:
            raise AssertionError(
                f"{case.case_id}: budget exceeded ({steps} > {case.max_steps})\n{output}"
            )

    for rel, before in snapshots.items():
        after = _file_text(workspace, rel)
        if after != before:
            raise AssertionError(
                f"{case.case_id}: unsolicited edit to {rel}\n"
                f"before: {before!r}\nafter: {after!r}"
            )

    for rel, expected in case.expected_files.items():
        actual = _file_text(workspace, rel).strip()
        if actual != expected.strip():
            raise AssertionError(
                f"{case.case_id}: {rel} expected {expected!r}, got {actual!r}"
            )


def run_live_gate(
    *,
    workspace: Path,
    aviona_exe: Path,
    timeout_per_case: int = 300,
    case_ids: set[str] | None = None,
) -> None:
    """Run the full L3 matrix; raise on first failure."""
    from framework.orchestration.session import ProbeFailedError, validate_slm_api_key

    try:
        probe = validate_slm_api_key()
    except (ProbeFailedError, RuntimeError) as exc:
        raise SystemExit(f"L3 gate: API probe failed: {exc}") from exc
    if not probe.ok:
        raise SystemExit("L3 gate: API probe failed")

    provider, model = _parse_runtime_facts(workspace)
    print(f"==> L3 live workspace: {workspace}")
    print(f"==> runtime provider={provider!r} model={model!r}")

    cases = [c for c in LIVE_MATRIX if case_ids is None or c.case_id in case_ids]
    if not cases:
        raise SystemExit("L3 gate: no matching live cases")

    for case in cases:
        print(f"  -> [{case.case_id}] {case.prompt}")
        _check_case(
            case,
            workspace=workspace,
            aviona_exe=aviona_exe,
            provider=provider,
            model=model,
            timeout=timeout_per_case,
        )
    print(f"==> L3 live gate PASSED ({len(cases)} cases)")


def main(argv: list[str] | None = None) -> int:
    """CLI entry for ``test-aviona.ps1 -Live``."""
    parser = argparse.ArgumentParser(description="Aviona L3 live acceptance gate")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(r"D:\thesis\aviona-test"),
        help="Live test cwd (default: D:\\thesis\\aviona-test)",
    )
    parser.add_argument(
        "--aviona",
        type=Path,
        default=None,
        help="Path to aviona executable (default: repo .venv)",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Run only the given case id (repeatable)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Per-prompt timeout in seconds",
    )
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[1]
    aviona_exe = args.aviona or (repo / ".venv" / "Scripts" / "aviona.exe")
    workspace = args.workspace
    if not workspace.is_dir():
        workspace = repo / "tests" / "fixtures" / "sample_repo"
    if not aviona_exe.is_file():
        print(f"error: aviona not found at {aviona_exe}", file=sys.stderr)
        return 1

    case_ids = set(args.case) if args.case else None

    try:
        run_live_gate(
            workspace=workspace.resolve(),
            aviona_exe=aviona_exe,
            timeout_per_case=args.timeout,
            case_ids=case_ids,
        )
    except AssertionError as exc:
        print(f"L3 FAIL: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f"L3 FAIL: timeout for {exc.cmd}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
