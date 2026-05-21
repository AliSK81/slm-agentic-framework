# Recommended Principles for Replan

User-stated constraints distilled for phase design.

---

## Do

1. **Framework-first phases** before Aviona polish or thesis table automation
2. **Typed completion** — `terminate{user_message, turn_type}` as the only normal success path
3. **Python enforces** budgets, permissions, read-only, write-guard from agent-declared turn_type
4. **Working memory** carries truncated tool results into next cycle structurally
5. **Honest failure** — `! reason` when completion impossible within budget
6. **Expand tests** with mock SLM queues that reproduce tool-loop failure modes
7. **Keep `--debug`** as first-class observability
8. **Separate tracks** in PROGRESS: `thesis_eval`, `framework_interactive`, `aviona_product`

---

## Do not

1. **Phrase → action** tables (deleted `intent.py`)
2. **Fixture aliases** (main file → main.py)
3. **Pre-turn Python answers** without LLM
4. **Scrape** rationale/tool output as default REPL detail
5. **Generic fallback** that marks wrong tool output as `ok`
6. **Regex classify_goal** routing
7. **Auto-revert** unsolicited writes
8. **Duplicate** reconciliation layers (fallback + synthesis + contract analyzer)

---

## Acceptable synthesis (if any — phase decision)

Only **post-agent** fallbacks tied to **recorded decisions**, not goal text:

| Trigger | Allowed? | User bias |
|---------|----------|-----------|
| code_edit ok, no terminate | `"Updated {path}."` | Tolerated if edit verified |
| read_file ok, no terminate | tool text / empty file msg | Tolerated vs missing message |
| list_dir ok, no terminate | listing | **Rejected** for non-list goals |
| disk read from goal | never | **Rejected** |
| run shell from goal | never | **Rejected** |

Prefer **strict mode**: no synthesis → always `unresolvable`.

---

## Phase sizing

- Each framework phase: **1 concern**, ≤5 tasks, unit tests, one commit
- Example sequence:
  1. Agent declares turn_type on cycle 1; Python binds budget
  2. Tool-result memory channel
  3. Mandatory terminate after read-only tool success
  4. Compound turn state machine (edit+run)
  5. Permission policy for inspect-run tools
  6. Remove Aviona keyword heuristics
  7. Expand live gate matrix

---

## PROGRESS.md seed (suggestion)

```yaml
current_phase: framework-interactive-1
phase_status: NOT_STARTED
blocker: "Replanned from temp/roadmap-replan-handoff; thesis-39 paused until interactive gate green"
active_roadmap: ROADMAP_FRAMEWORK_INTERACTIVE.md
thesis_track: paused_at_phase_39
aviona_track: v3_pending_framework
```

(Claude to finalize.)
