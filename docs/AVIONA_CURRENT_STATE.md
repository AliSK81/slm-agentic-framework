# Aviona — Current State Snapshot

**Date:** 2026-05-20  
**Package version:** `0.2.6` (`src/aviona/__init__.py`)  
**Repo:** `D:/thesis/agentic-ai`  
**Manual test workspace:** `D:/thesis/aviona-test`

---

## Track status (PROGRESS.md)

```yaml
current_phase: thesis-39
phase_status: PAUSED
active_roadmap: ROADMAP_PRODUCTION_AVIONA.md
aviona_track: DONE          # AVIONA-1 .. AVIONA-12 committed
last_aviona_commit: "4c638b3"
replan_note: Thesis 39-41 frozen until THESIS-RESUME approval
```

**Important:** AVIONA-12 marked the track DONE, but **0.2.0–0.2.6 live fixes are mostly uncommitted local work** on top of that commit (effects, fallbacks, verify_turn, journeys, install scripts).

---

## Intended product (from ROADMAP_PRODUCTION_AVIONA.md)

- Terminal REPL rooted at `cwd`.
- **One user line → one bounded `run_full_session(engine="graph")`** sharing persistent memory.
- Reuses thesis stack: LangGraph FSM, PlannerAgent, ExecutorAgent, Decision Cycle, bounded tools, MemoryStores.
- v1 DoD: `create hello.txt with "hi"` writes file + session JSONL under `~/.aviona/projects/<hash>/`.

---

## Source layout (`src/aviona/`)

| Module | Purpose |
|--------|---------|
| `cli.py` / `repl.py` | Entry point, interactive loop |
| `session.py` | **Turn adapter** — calls `run_full_session`, hints, fallbacks, revert |
| `effects.py` | Regex `classify_goal`, `analyze_turn_effects`, answer scraping |
| `verify_turn.py` | `TurnOutcomeVerifier` wraps framework verifier |
| `fallbacks.py` | Direct `read_file` / README summary when agent fails verification |
| `intent.py` | Local-only lines: hi, ok, thanks, bye (no API) |
| `runtime.py` | Provider/model line injected into session anchor |
| `permissions.py` | plan / default / auto modes |
| `snapshots.py` | Pre-edit snapshots + `aviona undo` |
| `store.py` | Session JSONL + meta |
| `render.py` | One-line REPL status (`ok`, `!`, steps, tokens) |

Framework entry: `src/framework/orchestration/session.py` → `run_full_session`.

---

## QA today

| Layer | Command | API key | What it proves |
|-------|---------|---------|----------------|
| L2 gate | `scripts/test-aviona.ps1` | No | 67 mocked unit/journey tests |
| L3 live | `scripts/test-aviona.ps1 -Live` | Yes | Minimal smoke (optional) |
| User | Manual REPL in `aviona-test` | Yes | **Primary integration test today** |

Journey matrix: `tests/aviona/JOURNEYS.md` (J1–J9, J3, J5, J6, J7, J8).

Install repair (Windows): `scripts/install-aviona.ps1` (corrupt `~*` dist-info, file lock on `aviona.exe`).

---

## What works (live + mocked)

- Editable install, `aviona --version`, `aviona doctor`
- Local chat: `hi`, `ok`, `thanks` — no agent turn
- `list files in this dir` — usually `list_dir`
- File create/edit when agent cooperates; undo via snapshots
- Mocked gate green after 0.2.x patches

---

## Live failures reported (post-v1)

| Prompt | Symptom |
|--------|---------|
| `what is this project` | Vacuous meta answer or README dump via fallback |
| `what is content of hello file?` | `list_dir` only, or fallback read |
| `ok` | Agent edited spurious file; verification failed after edit |
| `what is your model?` | 3k+ tokens, wrong “planner agent” answer |
| `what language model?` | 9.7k tokens, README project overview, memory truncation |
| `try to fastly reply with "salam"` | `ok` with **no detail line** (0.2.5); fixed in 0.2.6 for verification, still 3+ steps |

---

## Patch history (0.2.0 → 0.2.6)

Incremental fixes after AVIONA-12, not a redesign:

- TurnOutcomeVerifier + vacuous-ok rejection
- `classify_goal` kinds: write / read / read_content / explain / general
- Deterministic fallbacks (`read_file`, README summary)
- Auto-revert on unsolicited edits
- Runtime anchor (provider/model in constraints)
- Narrower explain fallback (project questions only)
- `requested_reply_text` for short verbatim replies
- Stopped appending tool_output blocks to REPL history (token bloat)

**User rejected:** routing model/meta questions to canned local replies (0.2.4) — “do not route it.”

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

Any replan must respect these or explicitly split “eval mode” vs “product mode.”

---

## Key paths for planners

```
ROADMAP_PRODUCTION_AVIONA.md
PROGRESS.md
tests/aviona/JOURNEYS.md
scripts/test-aviona.ps1
scripts/install-aviona.ps1
src/aviona/session.py
src/aviona/effects.py
src/aviona/fallbacks.py
src/framework/orchestration/session.py
configs/models.yaml          # aviona-daily profile
```
