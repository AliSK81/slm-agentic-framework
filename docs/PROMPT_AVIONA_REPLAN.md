# Prompt — Aviona Architecture Replan (paste into Claude)

Copy everything below the line into Claude (Opus or similar). Attach the files listed in **Attachments**.

---

## Your task

Plan an **architectural fix** for Aviona — the terminal REPL product built on the SLM Agentic Framework thesis engine. **Do not implement code.** Produce a replan document suitable for adding new roadmap phases.

We believe the problem is **architectural**, not a lack of regex patches. Live REPL testing fails while 67 mocked unit tests pass.

---

## Context (read attached files)

1. **`docs/AVIONA_CURRENT_STATE.md`** — version, track status, what works, patch history, QA layers  
2. **`docs/AVIONA_ARCHITECTURE_ISSUE.md`** — symptom→mechanism map, mismatches, planning questions  
3. **`ROADMAP_PRODUCTION_AVIONA.md`** — original v1 intent (AVIONA-1..12, marked DONE)  
4. **`tests/aviona/JOURNEYS.md`** — user journey matrix from bug reports  

Optional deep dives if you need implementation detail:

- `src/aviona/session.py` — turn adapter (main pain point)  
- `src/aviona/effects.py` — classification + verification scraping  
- `src/aviona/fallbacks.py` — post-hoc deterministic fixes  
- `src/framework/orchestration/session.py` — `run_full_session`  

---

## Hard constraints

- Respect the eight thesis rules in `ROADMAP_PRODUCTION_AVIONA.md` (memory stores, typed messages, Python-only transitions, Decision Cycle, truncation, anchor-first, append-only log, write-guard).
- Do **not** propose “route question X to a local canned answer” as the primary fix.
- Do **not** propose permanent README/`read_file` fallbacks without labeling them temporary.
- Keep `eval/` benchmark harness **frozen**; product changes must not require running live benchmarks.
- Plan for Windows dev (`pip install -e .`, `aviona.exe` file locks).

---

## Live failures you must explain (from manual testing in `D:\thesis\aviona-test`)

| Prompt | Bad outcome |
|--------|-------------|
| `what is this project` | Vacuous meta answer or irrelevant README dump |
| `what is content of hello file?` | Directory listing instead of file body |
| `ok` | Spurious file edit (`notes.txt`) then verification failure |
| `what is your model?` / `what language model?` | High tokens, wrong or irrelevant answers |
| `try to fastly reply with "salam"` | `ok` with no visible reply (3+ API steps, ~3.6k tok) |

---

## Deliverables (structured output)

### 1. Executive summary
- One paragraph: root cause  
- One paragraph: recommended direction  

### 2. Target architecture
- Mermaid diagram  
- Turn types (chat, read, write, explain, …) and **which orchestration each uses**  
- **User-visible outcome contract** (how REPL detail is produced — not scraped)  
- Single verification story aligned with UX  

### 3. What to remove or shrink
- Explicit list: `effects.classify_goal`, fallbacks, hint strings, dual verifiers, etc.  

### 4. Phased roadmap
- New phases (suggest filename: `ROADMAP_PRODUCTION_AVIONA_V2.md`)  
- Each phase: goal, tasks, test gate, commit message style  
- Mark `[REQUIRES_USER_INPUT]` where live API or product decisions needed  

### 5. Acceptance matrix
- **L2 mocked** (keep CI fast)  
- **L3 live** (real API, `aviona-test` workspace) — minimum prompts that block release  

### 6. Token / step budgets
- Targets per turn type; when full planner+executor graph is unacceptable  

### 7. Risks and open questions
- What requires thesis framework changes vs Aviona-only changes  

---

## Success criteria for your plan

A developer reading only your plan should understand:

- Why 0.2.x patches failed in live use  
- What replaces “one graph session per REPL line”  
- How a user always sees a correct detail line or a honest `!` with reason  
- How we test it (mock + live) without whack-a-mole regex journeys  

---

## Attachments checklist

Attach these files to Claude (minimum set):

| Priority | File |
|----------|------|
| **Required** | `docs/AVIONA_CURRENT_STATE.md` |
| **Required** | `docs/AVIONA_ARCHITECTURE_ISSUE.md` |
| **Required** | `ROADMAP_PRODUCTION_AVIONA.md` |
| **Required** | `tests/aviona/JOURNEYS.md` |
| Recommended | `src/aviona/session.py` |
| Recommended | `src/aviona/effects.py` |
| Recommended | `src/aviona/fallbacks.py` |
| Optional | `PROGRESS.md` |
| Optional | `scripts/test-aviona.ps1` |

Do **not** attach the whole repo unless Claude asks for more.
