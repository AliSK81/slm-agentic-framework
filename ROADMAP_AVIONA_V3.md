# ROADMAP — Aviona v3 (thin product layer)

> **Track id:** `aviona_product`. Starts **after** `ROADMAP_FRAMEWORK_INTERACTIVE.md` (FI-1…FI-7) is load-bearing.
> Aviona is the manual-test surface in `D:/thesis/aviona-test`, **not** the thesis contribution
> (`AVIONA_MVP_STATUS.md`). Keep it thin: anchor, contract verify, permissions UI, render, debug, store. All
> turn-type/budget/completion logic lives in the framework now; Aviona only **consumes** it.

## Phase Overview

```
AV3-1 → Consume framework ICP; delete Aviona budget/turn-type heuristics            [A04,F03]
AV3-2 → Permission UX for shell/pytest (mode banner, REPL confirm, auto for CI)     [A09,F11]
AV3-3 → Expand live gate from the real session matrix (contract-based)  [REQUIRES_USER_INPUT]
AV3-4 → Debug-session E2E matrix as CI-optional @pytest.mark.e2e        [REQUIRES_USER_INPUT]
AV3-5 → Docs + version bump (0.4.0)
```

Contract per phase: **Goal → Tasks → Acceptance tests → Commit**. Do **not** rebuild 0.2.x fallbacks, intent
routing, scrape, or auto-revert (`RECOMMENDED_PRINCIPLES.md` "Do not").

---

## AV3-1 — Consume framework ICP; delete Aviona heuristics

**Goal:** Aviona stops inferring turn type and budget; it reads them from the framework's declared
`turn_type`/`InteractiveTurnState` (FI-1) and renders the framework's typed outcome (FI-3/FI-4).

### Tasks
- `src/aviona/runtime.py` — **delete** `infer_interactive_max_steps()` keyword heuristics (A04/F03); stop
  passing `max_steps` into `run_turn`.
- `src/aviona/budgets.py` — consume the framework-declared `turn_type` for display only; remove any local cap
  inference.
- `src/aviona/session.py` — `run_turn` just builds the anchor (project rules + runtime facts + git + recent
  turns), compacts, and calls `framework.run_turn(interactive=True)`; no synthesis (it lives in FI-4).
- `src/aviona/render.py` — show the framework `user_message` verbatim, or `! reason` on `unresolvable`.

### Acceptance tests
```bash
pytest tests/unit/test_aviona_consumes_framework_turn_type.py
# no call to infer_interactive_max_steps (symbol deleted); budget/turn_type come from framework outcome
# render shows verbatim user_message; unresolvable → '! <reason>'
pytest tests/unit/test_aviona_session.py tests/unit/test_aviona_contract_matrix.py
```

### Commit
```
aviona-v3-1: consume framework ICP; delete Aviona budget/turn-type heuristics
```

---

## AV3-2 — Permission UX for shell/pytest

**Goal:** A clear REPL permission experience over the framework FI-6 policy: a mode banner, an inline confirm
for side-effecting shell in `default` mode, and `auto` for CI/non-interactive. No new permission *policy* in
Aviona (that is framework FI-6); this is UX only.

### Tasks
- `src/aviona/permissions.py` — render the active mode banner at session start; `default` mode prompts
  `[y/N]` for side-effecting shell via the injected reader (testable); `auto` skips prompts.
- `src/aviona/repl.py` — `--mode {plan,default,auto}` and `/mode`; `--yes`/non-interactive → `auto`.
- Inspect-run commands allowed by FI-6 do **not** prompt (read-only policy already cleared them).

### Acceptance tests
```bash
pytest tests/unit/test_aviona_permission_ux.py
# default mode + side-effecting shell → confirm prompt (mock reader yes/no)
# auto mode → no prompt; inspect-run (pytest) allowed by FI-6 → no prompt
```

### Commit
```
aviona-v3-2: permission UX (mode banner, confirm, auto for CI)
```

---

## AV3-3 — Expand the live gate from the real session matrix `[REQUIRES_USER_INPUT]`

**Goal:** Grow `scripts/live_gate.py` from 9 prompts to the matrix of real failures
(`SESSION_EVIDENCE.md`, `TEST_COVERAGE_GAPS.md`), using **contract-based** `must_contain` at the harness layer
only — never phrase handlers (deleted in v2-6).

> `[REQUIRES_USER_INPUT]` — needs API budget and author sign-off on each row's expected `must_contain`.

### Tasks
- `scripts/live_gate.py` — add rows: `inspect-main-file`, `inspect-explore-md`, `inspect-partial`
  (first-N-lines → substring or honest limit), `run-input`, `edit-test-run`, `anaphora-read`, `repeat-list`
  (latency assertion). Each asserts: declared `turn_type`, within-budget, no unsolicited writes, and a
  harness-layer `must_contain` for content.
- Keep matching at the harness only; no goal→answer routing reaches `src/`.

### Acceptance tests
```bash
scripts/test-aviona.ps1 -Live     # the expanded locked set passes against D:/thesis/aviona-test
```

### Commit
```
aviona-v3-3: expand live gate to the real session matrix (contract-based)
```

---

## AV3-4 — Debug-session E2E matrix as CI-optional `@pytest.mark.e2e` `[REQUIRES_USER_INPUT]`

**Goal:** Turn `scripts/debug_session.py` into a subprocess E2E test (20+ cases) marked `@pytest.mark.e2e`,
excluded from default CI, run nightly/on demand.

> `[REQUIRES_USER_INPUT]` — API budget.

### Tasks
- `tests/e2e/test_aviona_repl_matrix.py` — drive `aviona` as a subprocess over the AV3-3 matrix; assert
  contract outcomes; collect `--debug` traces on failure.
- `scripts/test-aviona.ps1 -Live` invokes it; default `pytest -m "not e2e"` excludes it.

### Acceptance tests
```bash
pytest tests/e2e/test_aviona_repl_matrix.py --collect-only   # structural, no key
pytest tests/e2e/test_aviona_repl_matrix.py -m e2e           # full run, needs key
```

### Commit
```
aviona-v3-4: debug-session E2E matrix (CI-optional)
```

---

## AV3-5 — Docs + version bump

**Goal:** Document the v3 thin-adapter model and bump the version.

### Tasks
- Update `docs/AVIONA_CURRENT_STATE.md` and `AVIONA_MVP_STATUS.md` to "all turn logic in framework; Aviona thin."
- `CHANGELOG`; bump `src/aviona/__init__.py` + `pyproject.toml` to `0.4.0`.

### Acceptance tests
```bash
pip install -e . && aviona --version    # prints 0.4.0
pytest tests/unit/test_aviona_*.py
```

### Commit
```
aviona-v3-5: docs + version 0.4.0
```

---

## Test gates (recap)

```bash
AV3-1: pytest tests/unit/test_aviona_consumes_framework_turn_type.py tests/unit/test_aviona_contract_matrix.py
AV3-2: pytest tests/unit/test_aviona_permission_ux.py
AV3-3: scripts/test-aviona.ps1 -Live          # [REQUIRES_USER_INPUT]
AV3-4: pytest tests/e2e/test_aviona_repl_matrix.py --collect-only   # full run [REQUIRES_USER_INPUT]
AV3-5: pip install -e . && aviona --version
```
