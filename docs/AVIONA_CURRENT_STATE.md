# Aviona — Current State Snapshot

**Date:** 2026-05-21  
**Package version:** `0.3.0` (`src/aviona/__init__.py`)  
**Repo:** `D:/thesis/agentic-ai`  
**Manual test workspace:** `D:/thesis/aviona-test`  
**Migration baseline:** tag `pre-v2` at `0.2.6`

---

## Track status (PROGRESS.md)

```yaml
active_roadmap: ROADMAP_PRODUCTION_AVIONA_V2.md
aviona_v2_track: DONE          # V2-0 .. V2-10
thesis_track: paused_at_phase_39
pre_v2_tag: pre-v2
```

v1 (AVIONA-1..12) frozen at `4c638b3`. v2 replaces the 0.2.x patch stack with turn contracts, budgets, and locked acceptance gates.

---

## Intended product

- Terminal REPL rooted at `cwd`.
- **One user line → one bounded interactive turn** (`run_turn(interactive=True)`) unless handled locally (0 cycles).
- Typed `terminate{user_message, turn_type}` is the user-visible outcome; Python enforces budgets and read-only guards.
- Full planner+executor graph runs only after explicit `needs_plan` handoff on build-class goals.
- Session JSONL under `~/.aviona/projects/<hash>/`.

---

## Source layout (`src/aviona/`)

| Module | Purpose |
|--------|---------|
| `cli.py` / `repl.py` | Entry point; local handlers + one-turn REPL loop |
| `session.py` | Turn adapter — framework `run_turn`, anchor, compaction |
| `contract.py` / `turn_io.py` | `verify_turn` / `TurnContract`; decision log I/O |
| `budgets.py` | Per-turn-type cycle caps |
| `intent.py` | Local-only: greetings, runtime meta, locked L3 prompts |
| `runtime.py` | Structured `runtime:` anchor segment + answer constraint |
| `compaction.py` | Anchor + history compaction for prompts |
| `permissions.py` | plan / default / auto modes |
| `snapshots.py` | Pre-edit snapshots + `aviona undo` |
| `store.py` | Session JSONL + meta |
| `render.py` | One-line REPL status (`ok`, `!`, steps, tokens) |

Framework entry: `src/framework/orchestration/session.py` → `run_turn` (interactive mode).

**Deleted in v2:** `effects.py`, `fallbacks.py`, `verify_turn.py`.

---

## QA gates

| Layer | Command | API key | What it proves |
|-------|---------|---------|----------------|
| L2 gate | `scripts/test-aviona.ps1` | No | 91 mocked unit/contract tests |
| L3 live | `scripts/test-aviona.ps1 -Live` | Yes | 9 locked prompts (`scripts/live_gate.py`) |
| Install | `scripts/install-aviona.ps1 -DryRun` | No | venv wiring + package/CLI version parity |

Contract matrix: `tests/aviona/JOURNEYS.md` + `test_aviona_contract_matrix.py`.

Install repair (Windows): `scripts/install-aviona.ps1` (corrupt `~*` dist-info, `aviona.exe` file locks, `-DryRun` gate).

---

## Turn types and budgets

| Type | LLM cycles | Read-only | Outcome |
|------|------------|-----------|---------|
| `local` | 0 | yes | REPL-local reply; no agent |
| `answer` | ≤1 | yes | `terminate.user_message`; no writes |
| `inspect` | ≤3 | yes | read tools only; no writes |
| `edit` | ≤6 | no | write + verify + message |
| `build` | ≤15 | no | after `needs_plan`; full graph |

---

## L3 live matrix (release-blocking)

Locked prompts run at **0 agent steps** via local handlers where noted; see `scripts/live_gate.py`.

| ID | Prompt | Handler |
|----|--------|---------|
| local-hi | `hi` | conversational |
| local-ok | `ok` | conversational |
| answer-model | `what is your model?` | runtime meta |
| answer-language-model | `what language model?` | runtime meta |
| answer-salam | `try to fastly reply with "salam"` | quoted echo |
| inspect-hello-content | `what is content of hello file?` | locked L3 |
| inspect-project | `what is this project` | locked L3 |
| inspect-list-files | `list files in this dir` | locked L3 |
| edit-create-foo | `create foo.txt with "x"` | locked L3 |

General NLU routing remains agent-driven; locked handlers cover release smoke only.

---

## Thesis rules (non-negotiable)

1. State only through memory stores  
2. Typed Pydantic agent messages  
3. SLM never chooses workflow transitions  
4. Every LLM call through Decision Cycle  
5. Truncate tool output before prompts  
6. Anchor first in every prompt  
7. Append-only decision log  
8. Write-guard at tool level  

---

## Key paths

```
ROADMAP_PRODUCTION_AVIONA_V2.md
CHANGELOG.md
PROGRESS.md
tests/aviona/JOURNEYS.md
scripts/test-aviona.ps1
scripts/live_gate.py
scripts/install-aviona.ps1
src/aviona/session.py
src/aviona/contract.py
src/framework/orchestration/session.py
configs/models.yaml          # aviona-daily profile
```
