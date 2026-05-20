# Aviona — UX spec (Claude Code–minimal)

**Product:** terminal agent in **one directory**. **Engine:** existing thesis framework (`run_full_session`, graph, Decision Cycle, tools). **Thesis eval:** separate; not the daily driver.

---

## User flow

```text
cd D:\my-project
aviona
```

1. Starts a **session** rooted at `cwd`.
2. You type prompts; Aviona **gathers context → acts → verifies** in a loop until done or you interrupt.
3. All file/shell actions stay under **cwd** (unless you explicitly allow wider scope).
4. Session state is **saved locally** (conversation + checkpoints); you can **resume** later.

Optional later: `aviona --continue`, `aviona --resume <id>`, `aviona --fork-session` — not required for v1.

---

## Agentic loop (same idea as Claude Code)

| Phase | What Aviona does | Thesis mapping |
|-------|------------------|----------------|
| **Gather context** | Read/search files, run read-only commands, load project rules | `READ_CONTEXT`, retrieval, `search_codebase`, `read_file` |
| **Take action** | Edit/create files, run builds/tests, git | `ACT`, file tools, `pytest_run`, shell (guarded) |
| **Verify** | Re-run tests, check compile, compare to your criteria | `EVALUATE` / quality gate / user-supplied checks |

Phases **blend**; the model chains tool uses and course-corrects. **You can interrupt** any time with a new prompt (next turn), not a new benchmark task.

**Harness:** Python orchestration + SLM — not the model choosing FSM transitions. **Model** proposes; **code** enforces transitions, write-guard, truncation, retries.

---

## Tools (v1 = reuse framework)

| Category | Aviona capability | Existing code |
|----------|-------------------|---------------|
| File | read, write, edit | `src/framework/tools/` |
| Search | codebase search | `search_codebase` |
| Execution | pytest, compile, guarded shell | `test_runner`, `sandbox` |
| Web | optional / later | out of v1 unless needed |
| Code intel | optional / later | plugins later |

No HuggingFace sampling in the main loop. Benchmarks stay in `eval/`.

---

## What loads at session start

| Source | File / store | Purpose |
|--------|--------------|---------|
| Project rules | `AVIONA.md` or `.aviona/PROJECT.md` (name TBD) | Conventions, stack, “always follow” rules (like `CLAUDE.md`) |
| Cwd | `Path.cwd()` | Workspace root; path jail |
| Git | optional read | branch, dirty files (like Claude Code) |
| Memory | framework stores | session-scoped working + episodic |
| Secrets | `%USERPROFILE%\.aviona\` or `.env` | API keys — never in repo |

**Compaction:** when context is full → truncate tool outputs first, then summarize (thesis truncation + working memory ceiling). Persistent rules live in **project markdown**, not in chat history.

---

## Sessions

- **One session** = one conversation JSONL (or sqlite thread) under `~/.aviona/projects/<hash>/`.
- **New session** = fresh context window; optional link to prior session summary later.
- **Checkpoints:** snapshot files **before** edit; undo restores snapshot (thesis checkpoints exist — wire to UX: `Esc` or `aviona undo`).
- **Resume:** reload same session id + append messages.

---

## Permissions (minimal v1)

| Mode | Behavior |
|------|----------|
| **Default** | Ask before shell commands with side effects; file writes via write-guard |
| **Auto-edit** | File edits allowed in cwd without per-file ask |
| **Plan** | Read-only tools + plan text; you approve before writes |

Config: `.aviona/settings.yaml` in project (allowlist commands like `pytest`, `git status`).

---

## Efficiency (your priority — without losing quality)

Focus **output tokens** and **visible noise**:

- Short user-facing replies (status lines, not essays).
- Tight planner/executor prompts; structured tool args (JSON).
- Aggressive **tool output truncation** before next LLM turn (already in framework — tune caps).
- **Compaction** policy when window fills (clear old tool blobs first).
- Optional: smaller model for executor, larger for planner only when needed.

Measure with existing `TrackingSLMClient` / `RunResult.tokens_total` — no new benchmark run required for tuning.

---

## What Aviona is **not** (v1)

- Not an IDE replacement (terminal first).
- Not `python -m eval.run_eval` / dataset tasks as the main UI.
- Not spending API tokens on full ablation matrices until you approve a **thesis sprint**.

---

## Thesis relationship

| Thesis piece | Aviona use |
|--------------|------------|
| Decision Cycle, graph, memory, error control | **Production engine** |
| `eval/`, cite allowlist, discriminative slice | **Frozen** until you approve benchmark phase |
| Insights from Aviona | Real file-edit sessions → qualitative chapter, failure taxonomy, token/latency tables |

Building Aviona **validates** the framework in practice; thesis numbers come **later** from `eval/` when you choose.

---

## v1 acceptance (no live benchmark matrix)

```bash
pip install -e .
cd tests/fixtures/sample_repo   # small fake repo
aviona                         # starts REPL
# prompt: "create hello.txt with content hi"
# file exists; session log written under ~/.aviona/
pytest tests/unit/test_aviona_session.py -v
```

---

## Roadmap output for Claude

Claude should produce `ROADMAP_PRODUCTION_AVIONA.md` with phases that implement **this spec** top to bottom, not a generic CLI toolkit.
