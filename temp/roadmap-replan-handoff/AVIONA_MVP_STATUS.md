# Aviona MVP Status (Thin Product Layer)

Aviona exists to **manual-test** the framework interactively in `D:/thesis/aviona-test`. It is not the thesis contribution — keep it minimal after framework fixes.

---

## Version & track

- **Package:** `0.3.0` (`src/aviona/__init__.py`)
- **v2 phases V2-0..V2-10:** marked DONE in `PROGRESS.md`
- **Real-world REPL:** still failing many prompts (see `PROBLEM_INVENTORY.md`)

---

## What Aviona should own (keep)

| Module | Responsibility |
|--------|------------------|
| `cli.py` / `repl.py` | Entry, `--debug`, one line → `session.run_turn` |
| `session.py` | Anchor, compaction, call `framework.run_turn(interactive=True)` |
| `contract.py` | TurnContract verify (budget, writes, message) |
| `budgets.py` | Caps per turn_type — **should consume framework-declared type** |
| `permissions.py` | plan/default/auto + REPL confirm |
| `runtime.py` | Anchor segment, meta constraints, **move step inference to framework** |
| `render.py` | Status line + verbatim detail or `!` |
| `debug_log.py` | Claude-style trace files |
| `store.py` / `snapshots.py` | Session JSONL, undo |

---

## What Aviona should NOT own (move/remove)

| Anti-pattern | Status |
|--------------|--------|
| `intent.py` phrase routing | **Deleted** |
| `infer_interactive_max_steps()` keyword heuristics | **Still in runtime.py — move to framework** |
| `interactive_turn_contract_hint()` long prose | Keep short; align with executor skills |
| Synthesis logic | **In framework session.py** — framework decision |
| Fixture-specific live handlers | **Removed** |

---

## QA today

| Layer | Command | Count |
|-------|---------|-------|
| L2 | `scripts/test-aviona.ps1` | ~91 unit/contract tests |
| L3 | `scripts/test-aviona.ps1 -Live` | 9 prompts (`live_gate.py`) |
| Debug | `scripts/debug_session.py` | 9 prompts, one session |

**Gap:** User's manual session had ~15+ distinct prompts; most not gated.

---

## v3 roadmap guidance (for Claude)

Keep Aviona v3 to **≤5 phases**, e.g.:

1. Consume framework Interactive Completion Protocol (delete local heuristics)
2. Permission UX for shell/pytest (mode banner, auto for CI)
3. Expand live gate from user session matrix (contract-based must_contain, not phrase handlers)
4. Debug session as CI optional `@pytest.mark.e2e`
5. Docs + version bump

Do **not** rebuild 0.2.x fallbacks or intent routing.

---

## Manual test workspace

`D:/thesis/aviona-test` — fixture repo with:
- `main.py` (greet), `hello.txt`, `solution.py` (empty), `bar.txt`, `AVIONA.md`, `README.md`, etc.

Any roadmap that hardcodes these filenames in framework code is **wrong**.
