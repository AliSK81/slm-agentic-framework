# Changelog — Aviona

## 0.4.0 — v3 thin adapter (2026-05-21)

### Added

- **Framework ICP consumption** (AV3-1) — Aviona reads `turn_type` and budgets directly from framework `load_interactive_budgets()`; deleted local `infer_interactive_max_steps` heuristics.
- **Permission UX** (AV3-2) — mode banner at session start; `default` mode prompts `[y/N]` for side-effecting shell; `auto` and inspect-run (`pytest --collect-only`) skip prompts; `--yes`/non-tty → auto.
- **Expanded L3 live gate** (AV3-3) — `scripts/live_gate.py` grown from 9 to 17 cases covering the real session failure matrix (`inspect-main-file`, `inspect-explore-md`, `inspect-partial`, `inspect-empty`, `repeat-list`, `run-input`, `anaphora-read`, `edit-test-run`); `must_contain_any` field; retry-on-failure; structural test `test_live_gate_matrix.py`.
- **E2E REPL matrix** (AV3-4) — `tests/e2e/test_aviona_repl_matrix.py`: 17 parametrized `@pytest.mark.e2e` tests driving `aviona` as a subprocess; `--debug` trace collected on failure; excluded from default CI via `-m "not e2e"`; invoked by `test-aviona.ps1 -Live`.

### Changed

- `scripts/test-aviona.ps1 -Live` — runs E2E REPL matrix after the live gate.
- `tests/aviona/JOURNEYS.md` — L3 table updated with all 17 locked cases.

## 0.3.0 — v2 migration close-out (2026-05-21)

### Added

- **Turn contract** (`contract.py`, `turn_io.py`) — product-level pass/fail from typed `terminate.user_message` and declared `turn_type`.
- **Per-turn budgets** (`budgets.py`) — cycle caps for `answer` / `inspect` / `edit` / `build`; read-only write-guard on interactive turns.
- **Interactive turn mode** — framework `run_turn(interactive=True)` loops until `terminate` or budget exhausted (no full graph for chat turns).
- **Runtime self-knowledge** — structured `runtime:` anchor facts + `runtime_answer_constraint` for model/provider questions.
- **L2 contract matrix** — `test_aviona_contract_matrix.py` replaces phrasing-regex journey tests.
- **L3 live gate** — `scripts/live_gate.py` (9 locked prompts); invoked by `scripts/test-aviona.ps1 -Live`.
- **Locked local handlers** — exact release prompts for meta model, salam echo, and L3 inspect/edit smoke (0 LLM cycles).
- **Windows install hardening** — `scripts/install-aviona.ps1 -DryRun`, corrupt `~*` dist-info cleanup, `aviona.exe` lock retry, version parity check.
- **Install gate tests** — `tests/unit/test_aviona_install.py`.

### Removed (patch-stack deletions)

- `src/aviona/effects.py` — regex `classify_goal` and turn-effect scraping.
- `src/aviona/fallbacks.py` — deterministic README/`read_file` fallbacks masking agent failure.
- `src/aviona/verify_turn.py` — duplicate `TurnOutcomeVerifier` (replaced by `contract.verify_turn`).
- `tests/unit/test_aviona_journeys.py` — phrasing-regex journeys (replaced by contract matrix).

### Changed

- `session.py` — thin adapter over framework interactive `run_turn`; no classification or fallback layers.
- `repl.py` — local path for conversational lines, runtime meta, quoted echo, and locked L3 prompts before agent turn.
- Framework `SessionOutcome.user_message`, interactive executor loop, `needs_plan` promotion guard, tool payload alias resolution.

### Baseline

- Tag `pre-v2` at **0.2.6** preserves the pre-migration patch stack for diff/revert.
