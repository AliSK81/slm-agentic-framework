# ROADMAP — Aviona (Production, Claude Code–minimal)

## Introduction

**Aviona** is a terminal agent you run inside a single project directory. You type `aviona`, get a
conversational session rooted at `cwd`, and the agent **gathers context → acts → verifies** in a loop —
editing files, running tests, and course-correcting — until the work is done or you interrupt with a new
prompt. It is a *thin product surface* over the existing thesis framework: the planner/executor agents, the
Decision Cycle, the LangGraph production path (`run_full_session(engine="graph")`), the bounded tools, the
memory stores, and the error-control layer are all **reused, not reimplemented**. Aviona adds only what a
daily-driver CLI needs: a packaged entry point, an interactive REPL, a cwd path-jail, project rules, local
session persistence, undo, permissions, and token-efficiency tuning.

**Relation to the thesis.** The thesis engine is the load-bearing core; Aviona validates it on real file-edit
work. The benchmark harness (`eval/`, `cite_allowlist.yaml`, the discriminative slice) stays **frozen** — it is
not the daily UI and Aviona never invokes `python -m eval.run_eval` in its loop. Insights from real Aviona
sessions (failure traces, token/latency numbers via `TrackingSLMClient`) feed the thesis qualitative chapter
later, but **no live benchmark matrices run until the author explicitly approves a thesis sprint** (see the
`THESIS-RESUME` section, every item `[REQUIRES_USER_INPUT]`).

**What v1 ships.** After **AVIONA-4** a user can `pip install -e .`, `cd` into any small repo, run `aviona`,
type `create hello.txt with "hi"`, and find the file written under `cwd` with a session log under
`~/.aviona/projects/<hash>/` — without touching `eval/`. AVIONA-5 through AVIONA-12 add efficiency, permissions,
undo, diagnostics, resume, and the locked acceptance harness.

The eight non-negotiable framework rules carry over unchanged: state flows only through memory stores; agents
exchange only typed Pydantic messages; the **SLM never chooses transitions** (Python/graph only); every LLM
call goes through the Decision Cycle; tool output is truncated before prompts; the anchor (goal + constraints)
comes first in every prompt; the decision log is append-only; the write-guard lives at the tool level.

---

## Architecture

```mermaid
flowchart TD
  user([user types a prompt]) --> repl["aviona REPL\n(src/aviona/repl.py)"]
  repl --> driver["AvionaSession.run_turn\n(src/aviona/session.py)"]
  driver -- "goal + constraints + verifier\n(one bounded turn)" --> rfs["run_full_session(engine='graph')\n(framework/orchestration/session.py)"]
  rfs --> graph["LangGraph FSM + SqliteSaver\n(Python next_state only)"]
  graph --> planner["PlannerAgent"] & executor["ExecutorAgent"]
  planner --> cycle["DecisionCycle\nREAD→PROPOSE→SELF_CHECK→CORRECT→ACT→RECORD\n(framework/control/cycle.py)"]
  executor --> cycle
  cycle --> tools["bounded tools (cwd-jailed)\nfile_tools / test_runner / search / compile_check"]
  cycle --> mem["MemoryStores (persistent, ~/.aviona)\nstate · decisions · subtasks · results"]
  driver --> verify["Verifier (Python)\nTestCode | RepoTests | NoOp(compile)"]
  driver --> store["session JSONL + checkpoints + snapshots\n(~/.aviona/projects/<hash>/)"]
  driver -. "interrupt = next prompt" .-> repl
```

The REPL owns the conversation; each user line becomes **one bounded `run_full_session` call** sharing a
persistent `MemoryStores`, checkpoint dir, and conversation log. The agent stack underneath is 100% the thesis
engine. Aviona's only engine-level additions are two backward-compatible parameters on `run_full_session`
(`verifier` and `probe`) and a `Verifier` protocol so free-form turns (no hidden tests) can be verified by
compile/repo-tests instead of a HumanEval-style assertion string.

---

## v1 Definition of Done (explicit)

After phases **AVIONA-1 → AVIONA-4** the following must succeed with **no live benchmark and no `eval/` call**:

```bash
pip install -e .
cd <any small repo>          # e.g. tests/fixtures/sample_repo
aviona
> create hello.txt with "hi"
# → hello.txt exists under cwd; a session JSONL line is written under ~/.aviona/projects/<hash>/
```

AVIONA-12 locks this with `tests/unit/test_aviona_session.py` (mocked SLM, no API key required).

---

## AVIONA PHASE 1 — Package & Console Entry Point

**Goal:** `pip install -e .` puts `aviona` on PATH (Windows-friendly, editable) and exposes a CLI skeleton; no
agent behavior yet, so the install/dev loop is unblocked first.

### Tasks
- `pyproject.toml` — add `[project.scripts]` with `aviona = "aviona.cli:main"`; keep `pythonpath = ["src"]`; add the new `src/aviona` package to the build (no new runtime deps yet; `prompt_toolkit` is optional, added in AVIONA-3).
- `src/aviona/__init__.py` — version constant.
- `src/aviona/cli.py` — `argparse` with subcommands `doctor` (stub) and bare `aviona` (REPL stub printing a banner), plus `--version`/`--help`; `main() -> int`.
- Reuse `framework.env.load_project_env` at startup for `.env` loading; never read or write secrets.

### Acceptance tests
```bash
pip install -e . && aviona --version          # prints version, exit 0
pytest tests/unit/test_aviona_cli.py -v        # argparse parses subcommands; main(["--help"]) == 0
```

### Commit
```
git commit -m "aviona-1: package + aviona console script (editable install)"
```

---

## AVIONA PHASE 2 — cwd Path-Jail + Turn Adapter over `run_full_session`

**Goal:** Run one user turn through the **existing** engine rooted at `cwd`, with all file tools jailed to
`cwd`, and make verification pluggable so free-form turns without hidden tests work — without building a second
agent stack.

### Tasks
- `src/framework/orchestration/verify.py` (new) — typed `Verifier` protocol returning a Pydantic `EvaluationResult`; implement `TestCodeVerifier` (wraps the existing `evaluate_workspace`) and `NoOpVerifier` (compiles changed `*.py` via `framework.tools.compile_check.py_compile_check`; passes when nothing to compile).
- `src/framework/orchestration/session.py` — two backward-compatible params on `run_full_session`: `verifier: Verifier | None = None` (default `None` → existing `test_code` path, thesis untouched) and `probe: bool = True`; gate the line `validate_slm_api_key()` behind `if probe:`. Make `test_code: str = ""` default; when empty and `verifier is None`, use `NoOpVerifier`.
- `src/aviona/session.py` (new) — `AvionaSession(cwd: Path)` holding `workspace=cwd`, a persistent `MemoryStores.sqlite(~/.aviona/projects/<hash>/memory.db)`, a checkpoint dir, and a stable REPL `session_root`. `run_turn(text) -> TurnResult` (Pydantic) builds `goal`/`constraints`/`verifier` for the line and calls `run_full_session(workspace=cwd, memory=<shared>, engine="graph", probe=False, verifier=…)`, then returns a concise `TurnResult`.
- Confirm the jail: `file_tools._resolve_path` already refuses paths outside `workspace`; add a regression test rather than new jail code.

### Acceptance tests (mocked SLM — no live API)
```bash
pytest tests/unit/test_verifier.py -v          # TestCodeVerifier parity w/ evaluate_workspace; NoOp compiles changed .py
pytest tests/unit/test_aviona_session.py::test_turn_creates_file_in_cwd -v
pytest tests/unit/test_aviona_session.py::test_write_outside_cwd_refused -v
pytest tests/unit/test_aviona_session.py::test_memory_db_persists_between_turns -v
```

### Commit
```
git commit -m "aviona-2: cwd-jailed turn adapter + pluggable Verifier (reuse run_full_session)"
```

---

## AVIONA PHASE 3 — Interactive REPL Loop

**Goal:** `aviona` starts a terminal REPL where each line is one bounded turn; Ctrl-C cancels the current turn
and returns to the prompt (it does not kill the process); output is short status, not essays.

### Tasks
- `src/aviona/repl.py` (new) — `run_repl(session, reader=default_reader, writer=print)`: loop read → `run_turn` → print one-line status; meta-commands `/exit`, `/help`, `/mode` (mode wired in AVIONA-7); catch `KeyboardInterrupt` per-turn and continue the loop.
- `default_reader` uses `prompt_toolkit` if importable (history, Windows-friendly) else falls back to `input()`; the `reader` is injectable so tests drive it with a scripted list (no TTY, no API).
- `src/aviona/cli.py` — bare `aviona` probes once at startup (`validate_slm_api_key()`), constructs `AvionaSession(Path.cwd())`, and enters `run_repl`. (A non-interactive `aviona -p "<prompt>"` one-shot may be added later as a convenience; the REPL is the primary surface.)

### Acceptance tests (no live API)
```bash
pytest tests/unit/test_aviona_repl.py -v
#   fake reader feeds ["create hello.txt ...", "/exit"] → run_turn called once, loop exits on /exit
#   KeyboardInterrupt raised inside a turn → loop survives and re-prompts
#   /help prints commands without invoking a turn
```

### Commit
```
git commit -m "aviona-3: interactive REPL loop with per-turn interrupt handling"
```

---

## AVIONA PHASE 4 — Project Rules (`AVIONA.md`) + Session Persistence  *(v1 DoD met here)*

**Goal:** Load project rules into the anchor at session start (like `CLAUDE.md`) and persist the conversation +
metadata locally, completing the v1 user journey.

### Tasks
- `src/aviona/project.py` (new) — locate rules at `./AVIONA.md` (preferred) or `./.aviona/PROJECT.md`; read, truncate to a config cap, and inject as additional `hard_constraints` / a leading `[PROJECT RULES]` segment so they ride the existing anchor (rule 6). Missing file → empty rules, no crash.
- `src/aviona/store.py` (new) — derive a stable project hash from `cwd`; create `~/.aviona/projects/<hash>/`; append each turn (user text, status, decision refs, `tokens_total`) to `session-<id>.jsonl` (append-only, rule 7); write/update `meta.json`. Scan-and-assert that no secret-shaped strings are persisted.
- `src/aviona/session.py` — pass loaded rules into `run_turn`; write a JSONL line after each turn.

### Acceptance tests
```bash
pytest tests/unit/test_aviona_project.py -v    # AVIONA.md injected into constraints; missing file safe
pytest tests/unit/test_aviona_store.py -v      # turn appends JSONL; project hash stable; no secrets written
```

### Commit
```
git commit -m "aviona-4: AVIONA.md project rules + local session persistence (v1 DoD)"
```

---

## AVIONA PHASE 5 — Output-Token Efficiency (Compact Prompts & Status)

**Goal:** Cut output tokens without losing task success — terser planner/executor replies, compact JSON-format
boilerplate, and one-line user-facing status instead of raw model/tool dumps.

### Tasks
- `src/framework/control/cycle.py` — make `_json_format_block` compact and emit the full example block only on the **first** prompt and on a schema-failure retry, not on every corrective round (keep parsing behavior identical; covered by existing cycle tests).
- `configs/models.yaml` — add daily-driver profile overrides (smaller `max_working_memory_tokens`, `skill_budget_tokens`) selectable by Aviona; thesis profiles unchanged.
- `src/aviona/render.py` (new) — map `SessionOutcome` → a single status line (e.g. `✓ edited solution.py · 3 steps · 1.2k tok`); never print raw tool output to the user.

### Acceptance tests
```bash
pytest tests/unit/test_token_efficiency.py -v
#   retry N>1 corrective prompt omits the full example block
#   render(outcome) is a single line under the configured width
#   WM builder honors the lowered daily-driver ceiling
pytest tests/integration/test_decision_cycle.py -v   # regression: cycle still parses/retries correctly
```

### Commit
```
git commit -m "aviona-5: output-token efficiency (compact prompts, terse status)"
```

---

## AVIONA PHASE 6 — Tool-Output Truncation Tuning + Compaction Policy

**Goal:** Keep context small under long sessions: tune per-tool caps for interactive use and, when the window
fills, evict old tool blobs first (deterministic, no LLM) before any summarization.

### Tasks
- `src/framework/error_control/truncation.py` — surface the per-tool `CAPS` via config and confirm `pytest_run` / `read_file` outputs are capped (head/tail) before entering prompts (tools already call `truncate`; this tunes the caps).
- `src/aviona/compaction.py` (new) — `compact(history, ceiling) -> history`: drop oldest tool-output blocks first; **always retain** the anchor and the most recent turn; pure and deterministic. (A bounded LLM summarization tier is explicitly deferred so v1 adds no LLM call outside the Decision Cycle — rule 4.)
- `src/aviona/session.py` — run `compact` on the rolling context before each turn.

### Acceptance tests
```bash
pytest tests/unit/test_truncation_caps.py -v   # oversized pytest output truncated to cap, head+tail preserved
pytest tests/unit/test_compaction.py -v        # tool blobs evicted first; anchor + last turn always kept; deterministic
```

### Commit
```
git commit -m "aviona-6: tool-output truncation tuning + deterministic compaction policy"
```

---

## AVIONA PHASE 7 — Permission Modes + Command Allowlist

**Goal:** A per-session permission layer over the existing sandbox: `plan` (read-only), `default` (ask before
side-effecting shell; writes via write-guard), `auto` (writes in cwd without per-file ask).

### Tasks
- `src/aviona/permissions.py` (new) — `Mode = Literal["plan","default","auto"]`; `PermissionGate.check(action) -> "allow"|"ask"|"deny"`. `plan` blocks `write_file`/`edit_file` and side-effecting shell; `default` asks before side-effecting shell; `auto` allows cwd writes silently. Layered **on top of** the framework `sandbox.SAFE_COMMANDS` allow-list (never widens it).
- `.aviona/settings.yaml` loader — project-local command allowlist (e.g. `pytest`, `git status`) and default mode.
- `src/aviona/repl.py` — `--mode` flag and `/mode` command; the "ask" path uses the injected `reader` so confirmations are testable.

### Acceptance tests
```bash
pytest tests/unit/test_permissions.py -v
#   plan blocks write_file; default asks before side-effect shell (mock confirm yes/no);
#   auto allows cwd write; command not in allowlist → deny; allowlist never widens SAFE_COMMANDS
```

### Commit
```
git commit -m "aviona-7: permission modes (plan/default/auto) + command allowlist"
```

---

## AVIONA PHASE 8 — Pre-Edit File Snapshots + `aviona undo`

**Goal:** Snapshot a file's prior content **before** any mutating edit so `aviona undo` can restore it; wire the
existing memory checkpoint per turn for state recovery.

### Tasks
- `src/aviona/snapshots.py` (new) — `SnapshotStore(project_dir)`: `before_mutation(path)` copies prior bytes into `~/.aviona/projects/<hash>/snapshots/<turn>/`; `undo_last() -> restored paths`.
- `src/aviona/tools.py` (new) — `snapshotting_write` / `snapshotting_edit` that **compose** `framework.tools.file_tools` (snapshot, then delegate to the real `write_file`/`edit_file` — no logic duplication, write-guard and AST gate preserved); Aviona's executor wiring uses these.
- `src/aviona/cli.py` — `aviona undo` subcommand. Per turn, also surface the `framework.memory.checkpoint.save_checkpoint` path already produced by `run_full_session`.

### Acceptance tests
```bash
pytest tests/unit/test_snapshots.py -v
#   edit then undo restores original bytes; undo with no snapshot → friendly no-op;
#   snapshots scoped to project dir; write-guard/AST gate still enforced through the wrapper
```

### Commit
```
git commit -m "aviona-8: pre-edit file snapshots + aviona undo"
```

---

## AVIONA PHASE 9 — `aviona doctor` (Probe-Only Diagnostics)

**Goal:** A fast environment/connectivity check that probes the active provider **without** starting a session,
reusing the existing probe-with-retry.

### Tasks
- `src/aviona/cli.py` — `doctor` subcommand: load env, print active provider/model (`framework.slm.config`), run `validate_slm_api_key()` (probe with retry, no decision cycle), report ok/error and exit code; never start a REPL or spend a turn.
- Secrets resolution order documented and implemented: `%USERPROFILE%\.aviona\.env` → project `.env`; never committed, never echoed.

### Acceptance tests
```bash
pytest tests/unit/test_aviona_doctor.py -v
#   mocked probe ok → exit 0, prints provider/model
#   mocked ProbeFailedError → non-zero exit + reason
#   missing/placeholder key → clear message, no probe attempted
```

### Commit
```
git commit -m "aviona-9: aviona doctor probe-only diagnostics"
```

---

## AVIONA PHASE 10 — Read-Only Git Context at Session Start

**Goal:** Surface a one-line repo status (branch + changed files) at session start, read-only, through the
guarded sandbox — useful orientation like Claude Code, with negligible token cost.

### Tasks
- `src/aviona/gitctx.py` (new) — `git_status(cwd)` via `git branch --show-current` and `git status --porcelain` executed through `framework.error_control.sandbox.safe_execute` (read-only commands only); parse to `{branch, changed_files}`; a non-git directory returns empty without error.
- `src/aviona/repl.py` — print branch + N changed files at startup; optionally fold a short summary into the anchor (kept tiny to respect the WM ceiling).

### Acceptance tests
```bash
pytest tests/unit/test_gitctx.py -v
#   porcelain parsed to changed-file count; non-git dir → empty, no crash; only sandbox-allowlisted git commands used
```

### Commit
```
git commit -m "aviona-10: read-only git context at session start"
```

---

## AVIONA PHASE 11 — Session Resume & Fork (Optional)

**Goal:** Reload a prior session's memory + conversation and continue, or fork a fresh session linked to a prior
summary.

### Tasks
- `src/aviona/store.py` — `list_sessions(project)`, `load_session(id)`: reattach the existing sqlite `MemoryStores` DB and the conversation JSONL for that project hash.
- `src/aviona/cli.py` — `aviona --continue` (latest session), `aviona --resume <id>`, `aviona --fork-session` (new id, link parent summary in `meta.json`).
- Resume appends to the same JSONL; fork starts a new JSONL referencing the parent.

### Acceptance tests
```bash
pytest tests/unit/test_aviona_resume.py -v
#   write a session → --continue reloads memory and appends; --resume <id> reattaches; fork creates linked new id;
#   unknown id → friendly error, no crash
```

### Commit
```
git commit -m "aviona-11: session resume and fork"
```

---

## AVIONA PHASE 12 — v1 Acceptance Harness (Sample Repo, Mocked End-to-End)

**Goal:** Lock the v1 Definition of Done with a fixture repo and a mocked-SLM end-to-end proving the
`create hello.txt` journey and the session log — entirely offline, no API key.

### Tasks
- `tests/fixtures/sample_repo/` (new) — a tiny fake repo (a couple of files + an `AVIONA.md`).
- `tests/unit/test_aviona_session.py` (the exact gate named in the UX spec) — drive `run_repl` with a fake reader feeding a `create hello.txt with "hi"` prompt and a mocked Decision Cycle that emits a `code_edit` creating the file; assert the file exists under the fixture cwd and a JSONL line was written under a temp `~/.aviona`.
- Document in `README`/`AVIONA.md` the exact v1 commands from the Definition of Done.

### Acceptance tests
```bash
pytest tests/unit/test_aviona_session.py -v    # the UX-spec v1 gate, mocked SLM, no API key
```

### Commit
```
git commit -m "aviona-12: v1 acceptance harness (sample_repo, mocked e2e)"
```

---

## THESIS-RESUME (deferred — every item `[REQUIRES_USER_INPUT]`)

These resume the **existing** thesis phases already specified in `ROADMAP.md` (phases 39–41) and the live
benchmark runs deferred by the author. **Do not start any of these without explicit approval and API/Docker
budget.** They are pointers, not rewrites — the specs live in `ROADMAP.md`; do not re-spec or merge them.

- **THESIS-RESUME-1 — ROADMAP phase 39** (curated-only LaTeX tables + figures). Gate: `pytest tests/unit/test_report_latex.py tests/unit/test_figures.py`. `[REQUIRES_USER_INPUT]`
- **THESIS-RESUME-2 — ROADMAP phase 40** (docs pass + zipped reproducibility bundle). Gate: `pytest tests/unit/test_repro_package.py && python scripts/make_repro_bundle.py --zip --dry-run`. `[REQUIRES_USER_INPUT]`
- **THESIS-RESUME-3 — ROADMAP phase 41** (e2e regression smoke + optional Redis pilot). Gate: `pytest tests/e2e/test_regression_smoke.py --collect-only`. `[REQUIRES_USER_INPUT]`
- **THESIS-RESUME-4 — Live discriminative A–D matrix + allowlist + curated report** (ROADMAP 31/32/33/35/36 live runs). Gate after run: `pytest tests/unit/test_cite_allowlist.py` with no skips for the new sections. `[REQUIRES_USER_INPUT]`

> Aviona may *opportunistically* capture real-session traces (decision JSONL, `RunResult.tokens_total`) that
> later enrich the thesis qualitative chapter and failure taxonomy — but writing thesis tables/figures or
> spending tokens on benchmark matrices stays behind these approval gates.

---

## Open Decisions (resolve before AVIONA-1)

1. **Package layout.** Recommend a new top-level `src/aviona/` package in the **same** distribution as
   `slm-agentic-framework` (one editable install, `framework.*` reused directly) rather than a separate
   distribution or `src/framework/cli/`. This satisfies "editable install picks up framework changes without
   reinstall friction." *Decision needed: confirm same-distribution.*
2. **Multi-turn model.** Recommend **one bounded `run_full_session` per user line**, sharing a persistent
   `MemoryStores` DB + checkpoint dir + conversation log across turns; cross-turn continuity is driver-managed
   (prior-turn summary injected into the next anchor) so the engine and graph stay untouched. *Alternative:
   one long-lived graph run spanning turns — heavier, risks reworking `next_state`/budget; not recommended for v1.*
3. **Verification for free-form turns.** Recommend the `Verifier` protocol (AVIONA-2): `NoOpVerifier`
   (compile changed `.py`) for free-form prompts, `TestCodeVerifier` for thesis parity, and a future
   `RepoTestsVerifier` (run the project's own test command) — keeping verification in **Python**, never the SLM.
4. **REPL library.** Recommend `prompt_toolkit` (history + Windows support) with a stdlib `input()` fallback and
   an injectable `reader` so the loop is unit-testable without a TTY. *Decision needed: accept the optional dep.*
5. **Project rules filename.** Recommend `AVIONA.md` at repo root (Claude Code's `CLAUDE.md` analog) with
   `.aviona/PROJECT.md` as an override. *Decision needed: confirm the canonical name.*

---

## Build Order & Test Gates (recap)

```bash
AVIONA-1:  pip install -e . && aviona --version && pytest tests/unit/test_aviona_cli.py
AVIONA-2:  pytest tests/unit/test_verifier.py tests/unit/test_aviona_session.py
AVIONA-3:  pytest tests/unit/test_aviona_repl.py
AVIONA-4:  pytest tests/unit/test_aviona_project.py tests/unit/test_aviona_store.py     # ← v1 DoD met
AVIONA-5:  pytest tests/unit/test_token_efficiency.py tests/integration/test_decision_cycle.py
AVIONA-6:  pytest tests/unit/test_truncation_caps.py tests/unit/test_compaction.py
AVIONA-7:  pytest tests/unit/test_permissions.py
AVIONA-8:  pytest tests/unit/test_snapshots.py
AVIONA-9:  pytest tests/unit/test_aviona_doctor.py
AVIONA-10: pytest tests/unit/test_gitctx.py
AVIONA-11: pytest tests/unit/test_aviona_resume.py
AVIONA-12: pytest tests/unit/test_aviona_session.py        # locks the v1 acceptance journey
```

> **Dependency order:** 1 → 2 → 3 → 4 is the v1 critical path. 5–6 (efficiency) come before polish per the
> author's priority. 7 (permissions) precedes 8 (undo) since undo is most useful once writes are gated. 9–11 are
> independent conveniences. 12 should run last and stay green for the rest of the project. No Aviona phase needs
> a live API key — all gates use mocked SLM or `--dry-run`; only `THESIS-RESUME` items spend budget.
