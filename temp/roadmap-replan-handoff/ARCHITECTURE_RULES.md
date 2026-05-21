# Architecture Rules (Non-Negotiable)

From `.cursor/rules/thesis-roadmap.mdc` and thesis design.

---

## Eight thesis rules

1. Agents pass state only through **memory stores**, never via messages
2. Agents communicate only via **typed Pydantic messages**, never free text
3. **SLM never decides workflow transitions** — Python only (`next_state()`)
4. Every LLM call goes through the **Decision Cycle**
5. **Truncate** every tool output before it enters a prompt
6. **Anchor** (goal + constraints) is always first in every prompt
7. **Decision Log** is append-only
8. **Write-guard** enforced at tool level

---

## Error handling conventions

| Component | On failure |
|-----------|------------|
| SLM client | `SLMResponse(error=...)` — never raise |
| Tools | Typed result with `ok=False` |
| Decision Cycle | `CycleResult(exhausted=True)` on SLM failure |
| Workflow nodes | Catch → transition to `ESCALATE` |
| Checkpoints | Atomic write (`.tmp` then rename) |

---

## Aviona v2 contracts (product)

- User-visible outcome: `terminate{user_message, turn_type}` only (verbatim in REPL)
- Turn types: `answer` | `inspect` | `edit` | `build` (local removed in v2 — all via agent)
- TurnContract: single pass/fail aligned with REPL display
- No scrape of rationale/tool output as default detail
- No auto-revert on unsolicited writes (write-guard + contract fail)

---

## Explicitly deleted patterns (v2-4+)

- `classify_goal` regex routing
- `pick_user_detail` / scrape stack
- `effects.py` / `fallbacks.py`
- `intent.py` local phrase handlers
- Deterministic README/read_file answer injection
- Auto-revert heuristics

---

## Allowed framework orchestration (not "hardcode")

These are **Python enforcement**, not phrase routing:

- Budget caps per turn_type
- Read-only tool allowlist for inspect turns
- Write-guard on edit tools
- Self-check validation of typed proposals
- Repeat-tool dedup within a turn
- Promotion to planner on typed `handoff{needs_plan}` only

**Not allowed:** goal substring → file path, goal substring → shell command, goal substring → skip LLM.

---

## Data boundaries

- Cross-module: **Pydantic v2** models only
- Paths: `pathlib.Path`
- Env: `python-dotenv` at module level
- Logging: no `print()` in library code
