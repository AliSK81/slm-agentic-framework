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
    must_contain_any: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()
    max_steps: int | None = None
    unchanged_files: tuple[str, ...] = ()
    expected_files: dict[str, str] = field(default_factory=dict)
    cleanup_files: tuple[str, ...] = ()


def _budget(turn_type: str) -> int:
    """Per-turn cycle cap from framework ``configs/models.yaml`` (FI-1)."""
    from framework.control.interactive import load_interactive_budgets

    return load_interactive_budgets()[turn_type]


LIVE_MATRIX: tuple[LiveCase, ...] = (
    LiveCase(
        "answer-hi",
        "hi",
        "answer",
        must_contain_any=("hi", "hello", "hey", "there", "how can"),
        max_steps=2,
    ),
    LiveCase(
        "answer-ok",
        "ok",
        "answer",
        must_contain_any=("ok", "sure", "noted", "yes", "ack"),
        max_steps=2,
        unchanged_files=("notes.txt",),
    ),
    LiveCase(
        "answer-model",
        "what is your model?",
        "answer",
        max_steps=2,
    ),
    LiveCase(
        "answer-language-model",
        "what language model?",
        "answer",
        max_steps=2,
    ),
    LiveCase(
        "answer-salam",
        'try to fastly reply with "salam"',
        "answer",
        must_contain=("salam",),
        max_steps=2,
    ),
    LiveCase(
        "inspect-hello-content",
        "Read hello.txt with read_file, then terminate turn_type inspect with user_message equal to the file content.",
        "inspect",
        must_contain=("hi",),
        max_steps=_budget("inspect"),
    ),
    LiveCase(
        "inspect-project",
        "Read README.md, then terminate turn_type inspect summarizing what this project is.",
        "inspect",
        must_contain_any=("aviona", "test workspace"),
        max_steps=_budget("inspect"),
    ),
    LiveCase(
        "inspect-list-files",
        "Use list_dir on . (not read_file), then terminate turn_type inspect; user_message must name hello.txt and main.py.",
        "inspect",
        must_contain=("hello.txt", "main.py"),
        max_steps=_budget("inspect"),
    ),
    LiveCase(
        "inspect-main-file",
        "Read main.py, then terminate turn_type inspect with a one-sentence summary mentioning greet.",
        "inspect",
        must_contain_any=("greet", "hello"),
        max_steps=_budget("inspect"),
        unchanged_files=("notes.txt",),
    ),
    LiveCase(
        "inspect-explore-md",
        "Use glob or read_file to find markdown files, then terminate turn_type inspect listing md filenames found.",
        "inspect",
        must_contain_any=(".md", "readme", "aviona"),
        must_not_contain=("no further action",),
        max_steps=_budget("inspect"),
        unchanged_files=("notes.txt",),
    ),
    LiveCase(
        "inspect-partial",
        "Read README.md, then terminate turn_type inspect with a short summary of only the title/first section (not the full install guide).",
        "inspect",
        must_contain_any=("aviona", "test workspace"),
        must_not_contain=("install-aviona.ps1",),
        max_steps=_budget("inspect"),
        unchanged_files=("notes.txt",),
    ),
    LiveCase(
        "inspect-empty",
        "Read solution.py with read_file, then terminate turn_type inspect (not answer) stating whether the file is empty.",
        "inspect",
        must_contain_any=("empty", "no content", "blank", "0 bytes", "zero"),
        max_steps=_budget("inspect"),
        unchanged_files=("notes.txt",),
    ),
    LiveCase(
        "repeat-list",
        "List files in this directory once, then terminate turn_type inspect with the listing.",
        "inspect",
        must_contain=("hello.txt",),
        max_steps=_budget("inspect"),
        unchanged_files=("notes.txt",),
    ),
    LiveCase(
        "run-input",
        'Run shell: python -c "from calculator import add; print(add(2, 3))" then terminate turn_type inspect showing stdout.',
        "inspect",
        must_contain=("5",),
        max_steps=_budget("inspect"),
        unchanged_files=("notes.txt",),
    ),
    LiveCase(
        "anaphora-read",
        'Use code_edit to create anaphora_probe.txt with content probe-data, read it with read_file, terminate turn_type edit with user_message containing probe-data.',
        "edit",
        must_contain=("probe-data",),
        max_steps=_budget("edit"),
        expected_files={"anaphora_probe.txt": "probe-data"},
        cleanup_files=("anaphora_probe.txt",),
    ),
    LiveCase(
        "edit-create-foo",
        'create foo.txt with "x"',
        "edit",
        must_contain=("foo.txt",),
        max_steps=_budget("edit"),
        expected_files={"foo.txt": "x"},
        cleanup_files=("foo.txt",),
    ),
    LiveCase(
        "edit-test-run",
        "code_edit gate_tiny_test.py with a trivial passing test, handoff needs_run, run pytest, terminate turn_type edit with pass/fail summary.",
        "edit",
        must_contain_any=("pytest", "pass", "passed"),
        max_steps=_budget("edit") + _budget("run"),
        expected_files={},
        cleanup_files=("gate_tiny_test.py",),
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

    status_lines = [
        line for line in output.splitlines() if " steps" in line and "|" in line
    ]
    if status_lines and not any("ok |" in line for line in status_lines):
        raise AssertionError(
            f"{case.case_id}: REPL status not ok\n{output}"
        )

    if "no further action" in output.lower():
        raise AssertionError(f"{case.case_id}: vacuous answer\n{output}")
    if re.search(r"^\s*!\s", output, re.MULTILINE) and "ok |" not in output:
        raise AssertionError(f"{case.case_id}: turn failed\n{output}")

    must_contain = _resolve_must_contain(case, provider=provider, model=model)
    for needle in must_contain:
        if needle.lower() not in output.lower():
            raise AssertionError(
                f"{case.case_id}: output missing {needle!r}\n{output}"
            )
    if case.must_contain_any:
        if not any(
            needle.lower() in output.lower() for needle in case.must_contain_any
        ):
            raise AssertionError(
                f"{case.case_id}: output missing any of {case.must_contain_any!r}\n{output}"
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
        last_error: AssertionError | None = None
        for attempt in range(2):
            try:
                _check_case(
                    case,
                    workspace=workspace,
                    aviona_exe=aviona_exe,
                    provider=provider,
                    model=model,
                    timeout=timeout_per_case,
                )
                last_error = None
                break
            except AssertionError as exc:
                last_error = exc
                if attempt == 0:
                    print(f"  !! [{case.case_id}] retry after: {exc}")
        if last_error is not None:
            raise last_error
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
