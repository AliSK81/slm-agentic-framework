"""Synthetic multi-step tasks with controlled interaction length L (RQ3)."""

from __future__ import annotations

import random
from pydantic import BaseModel


class MultiStepTask(BaseModel):
    """Parametric task requiring a chain of L dependent function implementations."""

    task_id: str
    required_steps: int
    prompt: str
    test_code: str
    entry_point: str
    reference_solution: str


def _task_seed(global_seed: int, level: int, index: int) -> int:
    """Deterministic per-task RNG seed from global seed, level L, and index."""
    return global_seed * 100_000 + level * 1_000 + index


def _chain_coefficients(level: int, index: int, global_seed: int) -> list[int]:
    """Return L integer offsets for the chained step functions."""
    rng = random.Random(_task_seed(global_seed, level, index))
    return [rng.randint(1, 9) for _ in range(level)]


def _expected_chain_value(x: int, coeffs: list[int]) -> list[int]:
    """Expected outputs for chain_step_0..chain_step_{L-1} at input x."""
    values: list[int] = []
    current = x
    for offset in coeffs:
        current = current + offset
        values.append(current)
    return values


def _build_chain_task(level: int, index: int, global_seed: int) -> MultiStepTask:
    """Build one L-step synthetic task with deterministic coefficients."""
    coeffs = _chain_coefficients(level, index, global_seed)
    x_input = 10 + index
    expected = _expected_chain_value(x_input, coeffs)

    func_lines: list[str] = []
    prompt_steps: list[str] = []
    for step in range(level):
        name = f"chain_step_{step}"
        if step == 0:
            body = f"    return x + {coeffs[0]}"
            dep = ""
        else:
            prev = f"chain_step_{step - 1}"
            body = f"    return {prev}(x) + {coeffs[step]}"
            dep = f" (must call {prev})"
        func_lines.append(f"def {name}(x: int) -> int:\n{body}\n")
        prompt_steps.append(
            f"{step + 1}. def {name}(x: int) -> int:{dep}\n"
            f"   Add {coeffs[step]} to the previous result."
        )

    reference_solution = "\n".join(func_lines)
    test_lines = [
        f"assert chain_step_{step}({x_input}) == {expected[step]}"
        for step in range(level)
    ]
    test_code = "\n".join(test_lines)
    entry_point = f"chain_step_{level - 1}"

    prompt = (
        f"Implement exactly {level} chained functions in solution.py. "
        "Each step must call the previous step (no copy-paste of logic).\n\n"
        + "\n".join(prompt_steps)
    )

    return MultiStepTask(
        task_id=f"multistep/L{level}/s{index:02d}",
        required_steps=level,
        prompt=prompt,
        test_code=test_code,
        entry_point=entry_point,
        reference_solution=reference_solution,
    )


def generate_multistep(
    levels: list[int] | None = None,
    per_level: int = 5,
    seed: int = 42,
) -> list[MultiStepTask]:
    """Generate synthetic tasks for each interaction-length level L.

    Inputs:
        levels: Required step counts (default ``[2, 4, 6, 8]``).
        per_level: Tasks per level.
        seed: Global RNG seed for reproducibility.

    Outputs:
        List of :class:`MultiStepTask` sorted by level then index.
    """
    step_levels = levels if levels is not None else [2, 4, 6, 8]
    tasks: list[MultiStepTask] = []
    for level in step_levels:
        if level < 1:
            raise ValueError(f"required_steps must be >= 1, got {level}")
        for index in range(per_level):
            tasks.append(_build_chain_task(level, index, seed))
    return tasks


def multistep_to_session(task: MultiStepTask) -> tuple[str, list[str], str]:
    """Map a multi-step task to session goal, constraints, and pytest body."""
    goal = task.prompt
    constraints = [
        f"Implement exactly {task.required_steps} functions in solution.py",
        f"Final entry point: {task.entry_point}",
        "Each chain_step_k must call chain_step_{k-1} for k > 0",
    ]
    return goal, constraints, task.test_code


def compile_check_source(task: MultiStepTask) -> str:
    """Return a single Python module combining reference solution and tests."""
    indented = "\n    ".join(line for line in task.test_code.strip().splitlines())
    return f"{task.reference_solution}\n\ndef __multistep_check() -> None:\n    {indented}\n"
