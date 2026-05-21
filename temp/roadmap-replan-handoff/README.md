# Roadmap Replan Handoff Pack

**Purpose:** Give Claude (or another planner) enough evidence to **replan the thesis framework roadmap** and a **minimal Aviona follow-on track** — without repeating hardcoded/boilerplate fixes.

**Generated:** 2026-05-21  
**Repo:** `D:/thesis/agentic-ai`  
**HEAD:** `4f3bc76` (latest: Aviona no-hardcode commit `10c80eb`)  
**Manual test workspace:** `D:/thesis/aviona-test`

---

## How to use this folder

1. Read **`PROMPT_FOR_CLAUDE_REPLAN.md`** — copy the entire block into Claude.
2. Attach or paste these files in order of priority:
   - `PROBLEM_INVENTORY.md` (master bug/scenario list)
   - `FRAMEWORK_ROOT_CAUSES.md` (thesis-level fixes)
   - `AVIONA_MVP_STATUS.md` (product/test layer only)
   - `FIXES_ALREADY_APPLIED.md` (do not re-propose)
   - `ARCHITECTURE_RULES.md` (non-negotiable)
   - `ROADMAP_CONTEXT.md` (existing plans)
   - `TEST_COVERAGE_GAPS.md`
   - `SESSION_EVIDENCE.md` (user-reported REPL runs)

3. Ask Claude to produce:
   - **`ROADMAP_PHASES_NEXT.md`** (or merge into `ROADMAP.md` after phase 39)
   - Optional: **`ROADMAP_PRODUCTION_AVIONA_V3.md`** (thin product layer on fixed framework)
   - Explicit **framework-first** phase ordering with acceptance tests per phase

---

## File index

| File | Contents |
|------|----------|
| `PROMPT_FOR_CLAUDE_REPLAN.md` | Copy-paste planner prompt |
| `PROBLEM_INVENTORY.md` | ~30+ scenarios, framework vs Aviona, status |
| `FRAMEWORK_ROOT_CAUSES.md` | Structural gaps (not symptom patches) |
| `AVIONA_MVP_STATUS.md` | REPL/product scope, what to keep thin |
| `FIXES_ALREADY_APPLIED.md` | Commits and changes already done |
| `ARCHITECTURE_RULES.md` | Thesis 8 rules + v2 contracts |
| `ROADMAP_CONTEXT.md` | Thesis phase 39 pause, Aviona v2 done, next files |
| `TEST_COVERAGE_GAPS.md` | L2/L3/debug vs real user sessions |
| `SESSION_EVIDENCE.md` | Transcript of user REPL problems |
| `KEY_CODE_PATHS.md` | Where to implement framework fixes |

---

## Planner constraints (user stated)

- Fix **framework (thesis) issues first** — Aviona is MVP/test harness.
- **No** phrase routing, fixture aliases, or Python-complete shortcuts.
- **No** large boilerplate layers (intent.py-style, scrape/fallback stacks).
- Prefer **typed contracts**, Decision Cycle completion protocol, Python-enforced budgets.
- One honest REPL outcome: agent `terminate{user_message}` or `! reason`.
