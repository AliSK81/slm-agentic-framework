# ROADMAP — SLM Agentic Framework
## Thesis: "An Agentic AI Programming Framework Focused on Memory Mechanisms and Control Logic Based on Small Language Models"

> **For the implementing agent:** Read PROGRESS.md first. Find your current phase. Implement it completely. Run all tests for that phase. Update PROGRESS.md. Commit. Move to the next phase. Do not wait for user input between phases unless a phase is marked `[REQUIRES_USER_INPUT]`.

---

## Architecture Reminder

Three modules, two agents, one framework:
- **Memory Module** → 4 typed stores (State, DecisionLog, SubTaskRegistry, ResultStore) + Working Memory builder
- **Control Logic Module** → Decision Cycle (per-LLM-call) + Workflow State Machine (session-level, LangGraph)
- **Error Control Infrastructure** → 9 deterministic mechanisms wrapping every LLM call and tool execution
- **Two agents** → Planner (Qwen2.5-Coder-7B) + Executor (Devstral-Small or equivalent)
- **Provider** → OpenRouter (not Ollama; same interface, remote endpoint)

---

## Phase Overview

```
PHASE 0  → Project bootstrap (git, venv, structure, env)
PHASE 1  → SLM client (OpenRouter)
PHASE 2  → Memory stores (4 stores + retrieval index)
PHASE 3  → Working Memory builder (L1 prompt assembler)
PHASE 4  → Error control infrastructure (9 mechanisms)
PHASE 5  → Bounded tool interface (run_tests, py_compile, file tools)
PHASE 6  → Decision Cycle (READ→PROPOSE→SELF_CHECK→CORRECT→ACT→RECORD)
PHASE 7  → Workflow State Machine (LangGraph, 7 states)
PHASE 8  → Agent implementations (Planner + Executor)
PHASE 9  → Integration: full session end-to-end
PHASE 10 → Evaluation harness (HumanEval, MBPP, SWE-bench adapters)
PHASE 11 → Ablation runner (configs A/B/C/D)
PHASE 12 → Qualitative trace analysis tools
```

Each phase has: **what to build → acceptance tests → commit message**.

---

## PHASE 0 — Project Bootstrap

**Goal:** Clean, reproducible project skeleton. Everything the agent needs to start coding.

### Tasks

```bash
# 0.1 Git init
git init
git config user.email "thesis@agent"
git config user.name "Thesis Agent"

# 0.2 Python virtual environment
python3 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

# 0.3 Install base dependencies
pip install --upgrade pip
pip install \
  langgraph>=0.2.50 \
  langchain-core \
  langchain-openai \
  redis \
  pydantic>=2.0 \
  httpx \
  pytest \
  pytest-asyncio \
  pytest-cov \
  python-dotenv \
  datasets \
  pyyaml \
  jinja2 \
  chromadb \
  sentence-transformers

pip freeze > requirements.txt

# 0.4 Create .env from template
cp .env.example .env   # agent must NOT fill in secrets; user does this
```

### Directory structure to create

```
slm-agentic-framework/
├── .env.example
├── .env                    # gitignored; user fills in OPENROUTER_API_KEY
├── .gitignore
├── ROADMAP.md
├── PROGRESS.md
├── README.md
├── requirements.txt
├── pyproject.toml
├── configs/
│   ├── models.yaml
│   ├── memory.yaml
│   └── eval.yaml
├── src/
│   └── framework/
│       ├── __init__.py
│       ├── slm/
│       │   ├── __init__.py
│       │   └── client.py
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── stores.py
│       │   ├── retrieval.py
│       │   ├── reflection.py
│       │   └── checkpoint.py
│       ├── control/
│       │   ├── __init__.py
│       │   ├── cycle.py
│       │   ├── self_check.py
│       │   ├── workflow.py
│       │   ├── ledger.py
│       │   └── budget.py
│       ├── orchestration/
│       │   ├── __init__.py
│       │   ├── planner.py
│       │   ├── executor.py
│       │   ├── messages.py
│       │   └── graph.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── test_runner.py
│       │   ├── compile_check.py
│       │   ├── file_tools.py
│       │   └── search.py
│       └── error_control/
│           ├── __init__.py
│           ├── parser.py
│           ├── quality.py
│           ├── truncation.py
│           ├── thinking.py
│           ├── watchdog.py
│           └── sandbox.py
├── eval/
│   ├── __init__.py
│   ├── datasets/
│   │   ├── humaneval_adapter.py
│   │   ├── mbpp_adapter.py
│   │   └── swebench_adapter.py
│   ├── metrics/
│   │   ├── sr.py
│   │   └── cer.py
│   ├── scenarios/
│   │   ├── ablation.py
│   │   └── agent_count.py
│   └── run_eval.py
├── traces/
│   └── .gitkeep
├── checkpoints/
│   └── .gitkeep
└── tests/
    ├── __init__.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_slm_client.py
    │   ├── test_memory_stores.py
    │   ├── test_retrieval.py
    │   ├── test_self_check.py
    │   ├── test_error_control.py
    │   └── test_tools.py
    ├── integration/
    │   ├── __init__.py
    │   ├── test_decision_cycle.py
    │   ├── test_workflow.py
    │   └── test_memory_control_integration.py
    └── e2e/
        ├── __init__.py
        ├── test_humaneval_sample.py
        └── test_full_session.py
```

### `.env.example` content

```
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Primary model for Executor (code generation)
EXECUTOR_MODEL=mistralai/devstral-small

# Primary model for Planner (planning and decomposition)
PLANNER_MODEL=qwen/qwen-2.5-coder-7b-instruct

# Fallback model (cheaper, for retries and simple tasks)
FALLBACK_MODEL=qwen/qwen-2.5-coder-7b-instruct

# Memory backend: "redis" or "sqlite"
MEMORY_BACKEND=sqlite

# Redis connection (only if MEMORY_BACKEND=redis)
REDIS_URL=redis://localhost:6379

# SQLite path (only if MEMORY_BACKEND=sqlite)
SQLITE_PATH=./data/framework.db

# Workspace root for tool execution
WORKSPACE_ROOT=./workspace

# Checkpoint directory
CHECKPOINT_DIR=./checkpoints

# Trace output directory
TRACE_DIR=./traces

# Step budget defaults
DEFAULT_MAX_STEPS=20
DEFAULT_MAX_RETRIES=3

# Thinking budget (tokens; 0 = disabled)
THINKING_BUDGET=2048
```

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "slm-agentic-framework"
version = "0.1.0"
description = "SLM-based multi-agent programming framework (MSc thesis)"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short"

[tool.coverage.run]
source = ["src/framework"]
omit = ["tests/*"]
```

### `configs/models.yaml`

```yaml
profiles:
  devstral-small:
    openrouter_id: "mistralai/devstral-small"
    context_limit: 32768
    effective_context: 16000
    thinking_budget: null
    max_working_memory_tokens: 750
    tool_output_caps:
      pytest_run: 5000
      py_compile: 2000
      read_file: 12000
      search_codebase: 2000
    skill_budget_tokens: 150
    timeout_by_role:
      executor: 90
      tool_call: 30
    tool_call_format: "json"

  qwen2.5-coder-7b-instruct:
    openrouter_id: "qwen/qwen-2.5-coder-7b-instruct"
    context_limit: 32768
    effective_context: 12000
    thinking_budget: null
    max_working_memory_tokens: 650
    tool_output_caps:
      pytest_run: 4000
      py_compile: 1500
      read_file: 8000
      search_codebase: 1500
    skill_budget_tokens: 120
    timeout_by_role:
      planner: 60
      executor: 75
      tool_call: 30
    tool_call_format: "json"
```

### `configs/memory.yaml`

```yaml
backend: sqlite   # override with env MEMORY_BACKEND
sqlite:
  path: "./data/framework.db"
redis:
  url: "redis://localhost:6379"
  ttl_seconds: 86400   # 24h TTL on session data

retrieval:
  top_k: 3
  max_item_tokens: 150
  alpha_recency: 0.2
  alpha_importance: 0.5
  alpha_relevance: 0.3
  decay_factor: 0.995   # per hour, from Generative Agents paper

reflection:
  trigger_retry_threshold: 1   # reflect after this many retries on same subtask
  max_reflections_per_subtask: 3
```

### `configs/eval.yaml`

```yaml
humaneval:
  sample_size: 50
  seed: 42
  difficulty_split: {easy: 20, medium: 20, hard: 10}

mbpp:
  sample_size: 50
  seed: 42

swebench:
  variant: "lite"   # lite=300 tasks; we use subset
  sample_size: 30
  seed: 42
  docker_required: true

step_budgets:
  humaneval: {max_steps: 10, max_retries: 3}
  mbpp:      {max_steps: 15, max_retries: 3}
  swebench:  {max_steps: 25, max_retries: 3}

ablation_configs:
  A: {memory: false, control: false, error_control: false}
  B: {memory: true,  control: false, error_control: false}
  C: {memory: false, control: true,  error_control: false}
  D: {memory: true,  control: true,  error_control: true}
```

### Acceptance tests for Phase 0

```bash
# All of these must pass before Phase 0 is DONE
python -c "import langgraph; print('langgraph ok')"
python -c "import pydantic; print('pydantic ok')"
python -c "import redis; print('redis ok')"
python -c "from dotenv import load_dotenv; print('dotenv ok')"
pytest tests/ --collect-only   # must collect without errors (no test failures yet, just collection)
```

### Commit
```
git add -A && git commit -m "phase-0: project bootstrap, skeleton, configs"
```

---

## PHASE 1 — SLM Client (OpenRouter)

**Goal:** A single, typed client that all agents use to call any model via OpenRouter. Handles retries, timeouts, structured output, and model profile loading.

### `src/framework/slm/client.py` — full specification

```python
"""
Unified SLM client for OpenRouter.
All agents use this; no direct HTTP calls elsewhere.

Key behaviors:
- Loads model profile from configs/models.yaml
- Enforces per-role timeout via watchdog
- Requests JSON output mode when tool_call_format == "json"
- Returns raw text; callers (error_control/parser.py) handle parsing
- Retries on 429 / 503 with exponential backoff (max 3 retries)
- Never raises on model error; returns ErrorResponse instead
"""

from dataclasses import dataclass
from typing import Literal
import os, httpx, time, yaml
from pathlib import Path
from pydantic import BaseModel

class ModelProfile(BaseModel): ...   # matches configs/models.yaml schema
class SLMResponse(BaseModel):
    content: str
    model: str
    tokens_used: int
    elapsed_ms: int
    error: str | None = None

class SLMClient:
    def __init__(self, profile_name: str): ...
    def call(self, messages: list[dict], role: str, json_mode: bool = True) -> SLMResponse: ...
    def _call_with_retry(self, payload: dict, timeout_s: int) -> dict: ...
```

The client must:
- Read `OPENROUTER_API_KEY` from environment
- Load `configs/models.yaml` and parse the matching profile
- Send requests to `https://openrouter.ai/api/v1/chat/completions`
- Include headers: `HTTP-Referer: thesis-framework`, `X-Title: SLM-Thesis`
- Use `response_format: {"type": "json_object"}` when `json_mode=True`
- Apply per-role timeout from profile (`timeout_by_role[role]`)
- Return `SLMResponse(error=...)` on failure, never raise

### Acceptance tests — `tests/unit/test_slm_client.py`

```python
# These tests use httpx mock — no real API calls in unit tests

def test_client_loads_profile():
    """Client reads model profile from configs/models.yaml correctly."""

def test_client_returns_slm_response_on_success():
    """Mocked 200 response → SLMResponse with content, no error."""

def test_client_returns_error_response_on_429():
    """429 after 3 retries → SLMResponse(error='rate_limited'), no raise."""

def test_client_returns_error_response_on_timeout():
    """Timeout → SLMResponse(error='timeout'), no raise."""

def test_client_json_mode_sets_response_format():
    """json_mode=True → request payload contains response_format."""

def test_client_applies_role_timeout():
    """role='planner' → uses profile.timeout_by_role['planner']."""
```

All 6 tests must pass (mocked, no real API calls).

### Commit
```
git add -A && git commit -m "phase-1: SLM client (OpenRouter, typed, retry, timeout)"
```

---

## PHASE 2 — Memory Stores

**Goal:** Four typed stores (State, DecisionLog, SubTaskRegistry, ResultStore) backed by SQLite or Redis, plus a Retrieval Index with the Generative Agents scoring formula.

### Data models — `src/framework/memory/stores.py`

All models are Pydantic v2. Every write method also appends a `RetrievalItem` to the index. Write discipline per store:

| Store | Write rule |
|---|---|
| StateStore | Versioned — each write is a new snapshot with `step_index`. Never overwrite. |
| DecisionLog | Append-only — never update or delete. |
| SubTaskRegistry | Mutable only via `set_status(task_id, new_status)`. |
| ResultStore | Append-only — never update or delete. |

```python
# Key schemas (implement all fields exactly as specified in solution path §2)

class StateEntry(BaseModel):
    session_id: str
    step_index: int
    artifact_hash: str
    tests_status: dict          # {passed: N, failed: M, errors: K}
    open_subtasks: list[str]
    timestamp: datetime

class DecisionEntry(BaseModel):
    session_id: str
    decision_id: str
    step_index: int
    by_agent: Literal["planner", "executor"]
    kind: Literal["plan_step","code_edit","tool_call","handoff","terminate","reflection","quality_failure"]
    payload: dict
    rationale: str
    references: list[str]       # e.g., ["state:17", "result:t-019"]
    self_check: SelfCheckRecord
    timestamp: datetime

class SelfCheckRecord(BaseModel):
    verdict: Literal["pass","fail","exhausted"]
    issues: list[Issue]

class Issue(BaseModel):
    kind: Literal["schema_violation","contradiction","scope_violation","empty","loop"]
    detail: str

class SubTask(BaseModel):
    task_id: str
    parent_session_id: str
    description: str
    status: Literal["open","in_progress","done","abandoned"]
    owner: Literal["planner","executor"]
    depends_on: list[str]
    result_ref: str | None
    attempt_count: int

class InteractionResult(BaseModel):
    result_id: str
    kind: Literal["pytest_run","py_compile","syntax_check"]
    passed: bool
    failed_tests: list[str]
    error_message: str | None
    stdout: str                 # truncated to cap before storage
    stderr: str
    exit_code: int
    linked_subtask: str
    timestamp: datetime

class RetrievalItem(BaseModel):
    item_ref: str               # "decision:d-031" or "state:17" etc.
    text_summary: str
    importance: float           # 0.5 or 1.0
    written_at: datetime
    last_accessed: datetime
```

### `src/framework/memory/retrieval.py`

Implements the scoring formula from Park et al. (Generative Agents, 2023):

```python
def score(item: RetrievalItem, query: str, now: datetime) -> float:
    """
    score = α_rec * recency + α_imp * importance + α_rel * keyword_overlap
    recency = decay_factor ^ hours_since_last_access
    importance = item.importance (0.5 or 1.0, pre-assigned)
    keyword_overlap = bigram_hits*2 + word_hits*1, normalized
    """

def retrieve_top_k(index: list[RetrievalItem], query: str, k: int = 3) -> list[RetrievalItem]:
    """Score all items, return top-k. Each item capped at 150 tokens when serialized."""
```

### Backend abstraction

```python
class MemoryBackend(Protocol):
    """Abstract interface; SQLiteBackend and RedisBackend both implement this."""
    def write(self, store: str, key: str, value: dict) -> None: ...
    def read(self, store: str, key: str) -> dict | None: ...
    def query(self, store: str, filters: dict) -> list[dict]: ...
    def append(self, store: str, value: dict) -> None: ...
```

Implement `SQLiteBackend` fully. `RedisBackend` can be a stub that raises `NotImplementedError` if `MEMORY_BACKEND=sqlite` — implement Redis fully only if needed.

### Acceptance tests — `tests/unit/test_memory_stores.py`

```python
def test_state_store_write_creates_new_snapshot():
    """Writing twice creates two entries with step_index 0 and 1."""

def test_decision_log_is_append_only():
    """No update or delete method exists on DecisionLog."""

def test_decision_log_get_last_n():
    """get_last_N(session_id, 3) returns the 3 most recent entries."""

def test_subtask_status_transition():
    """set_status('open' → 'in_progress') succeeds; 'done' → 'open' raises."""

def test_result_store_append():
    """Two results for same subtask are both stored and retrievable."""

def test_retrieval_item_appended_on_every_write():
    """After writing to DecisionLog, retrieval index has one new item."""

def test_retrieval_scoring_ranks_recent_higher():
    """Two items same importance/relevance; newer one scores higher."""

def test_retrieval_scoring_ranks_important_higher():
    """Two items same recency/relevance; importance=1.0 scores higher than 0.5."""

def test_retrieve_top_k_returns_k_items():
    """10 items in index, k=3 → 3 items returned."""

def test_sqlite_backend_persists_across_instances():
    """Write with instance A, read with fresh instance B → data present."""
```

All 10 tests must pass.

### Commit
```
git add -A && git commit -m "phase-2: memory stores (4 stores, retrieval scoring, SQLite backend)"
```

---

## PHASE 3 — Working Memory Builder

**Goal:** Assembles the L1 Working Memory struct from L2 stores. This is what goes into every LLM prompt. Must stay under token ceiling.

### `src/framework/memory/stores.py` addition — `WorkingMemory`

```python
class WorkingMemory(BaseModel):
    original_goal: str
    hard_constraints: list[str]
    agent_role: str
    agent_scope: str
    current_subtask: str
    subtask_id: str
    retrieved_items: list[str]      # max 3 items, each max 150 tokens
    last_error: str | None
    retry_count: int
    skill_card: str | None

    def to_prompt_prefix(self) -> str:
        """Serializes to the prompt prefix string. Token count enforced here."""

    def token_count(self) -> int:
        """Rough token estimate: len(text) // 4."""
```

### `WorkingMemoryBuilder`

```python
class WorkingMemoryBuilder:
    def __init__(self, memory: MemoryStores, profile: ModelProfile): ...

    def build(self,
              session_id: str,
              agent_role: str,
              current_subtask: str,
              subtask_id: str,
              last_error: str | None = None,
              retry_count: int = 0) -> WorkingMemory:
        """
        1. Load goal and constraints from SubTaskRegistry (parent session)
        2. Retrieve top-3 items from Retrieval Index using current_subtask as query
        3. Select skill card by priority: error_recovery > recency > intent
        4. Assemble WorkingMemory
        5. Assert total token count <= profile.max_working_memory_tokens
        """
```

### Skill cards — `src/framework/slm/skills/`

Create these as YAML files loaded at startup:

- `planner_decompose.yaml` — how to write a valid plan step JSON
- `planner_dispatch.yaml` — how to write a valid DISPATCH message
- `executor_code_edit.yaml` — how to use edit_file correctly (old_string must be exact)
- `executor_test_recovery.yaml` — what to do when pytest fails
- `executor_compile_error.yaml` — how to read and fix a compile error

Each card: `name`, `trigger_keywords: list[str]`, `content: str` (80–150 tokens).

### Acceptance tests — `tests/unit/test_retrieval.py`

```python
def test_working_memory_stays_under_token_ceiling():
    """Builder raises if assembled WM exceeds profile.max_working_memory_tokens."""

def test_anchor_always_present():
    """goal and hard_constraints always appear in to_prompt_prefix() output."""

def test_retrieved_items_capped_at_3():
    """Even if 10 items in index, WM.retrieved_items has at most 3."""

def test_retrieved_item_text_capped_at_150_tokens():
    """Items with long text are truncated to 150 tokens each."""

def test_skill_card_selected_by_error_signal():
    """last_error containing 'SyntaxError' → executor_compile_error card selected."""

def test_skill_card_none_when_no_match():
    """No matching card → skill_card is None, no crash."""
```

All 6 tests must pass.

### Commit
```
git add -A && git commit -m "phase-3: working memory builder, skill cards, prompt prefix"
```

---

## PHASE 4 — Error Control Infrastructure

**Goal:** All 9 deterministic error-control mechanisms. No LLM calls. Pure Python.

### Implementation order and specs

**4.1 — `src/framework/error_control/parser.py`**

Repairs 8 malformed JSON patterns from SLM output:
1. Fenced with ` ```json ` … ` ``` `
2. Fenced with ` ```tool ` … ` ``` `
3. Wrapped in `<decision>…</decision>` tags
4. Bare JSON (no wrapper, starts with `{`)
5. Trailing commas before `}` or `]`
6. Single-quoted string keys
7. Missing closing `}` (truncated output)
8. JSON strings with literal newlines

```python
def parse_decision(raw_text: str, schema: type[BaseModel]) -> BaseModel | None:
    """Try native parse → extract → repair → validate schema → return or None."""
```

**4.2 — `src/framework/error_control/quality.py`**

Three failure modes:
```python
class QualityGate:
    def check(self, raw_text: str, parsed: BaseModel | None,
              recent_decisions: list[DecisionEntry]) -> QualityResult:
        # FAIL if empty_response
        # FAIL if parsed is None
        # FAIL if loop detected (same kind+hash in last 5, count >= 3)
```

**4.3 — `src/framework/error_control/truncation.py`**

Asymmetric truncation: first half + last quarter.
```python
CAPS = {"pytest_run": 4000, "py_compile": 2000, "read_file": 8000,
        "syntax_check": 1500, "search_codebase": 2000}

def truncate(text: str, tool: str) -> str:
    """Apply cap for tool. Asymmetric: head=75%, tail=25%."""
```

**4.4 — `src/framework/error_control/thinking.py`**

ThinkingBudget class (used only for models with thinking tokens).
```python
class ThinkingBudget:
    def __init__(self, limit: int = 2048): ...
    def feed(self, token: str) -> bool: ...     # False = abort
    def reuse_context(self) -> str: ...
```

**4.5 — `src/framework/error_control/watchdog.py`**

```python
def call_with_timeout(fn: Callable, args: dict, timeout_s: int) -> Any | TimeoutResult:
    """ThreadPoolExecutor with timeout. Returns TimeoutResult on timeout, never raises."""
```

**4.6 — `src/framework/error_control/sandbox.py`**

```python
SAFE_COMMANDS = {"python", "python3", "pytest", "py_compile",
                 "cat", "ls", "find", "diff", "echo", "ast"}

def safe_execute(cmd: str, cwd: Path, timeout_s: int = 30) -> SubprocessResult:
    """Allow-list check → subprocess → truncated stdout/stderr."""
```

**4.7 — Write-guard** (in `src/framework/tools/file_tools.py`, phase 5 — but spec here)

**4.8 — AST-gated edit** (in `src/framework/tools/file_tools.py`, phase 5)

**4.9 — Incremental checkpointing** — `src/framework/memory/checkpoint.py`
```python
def save_checkpoint(session_id: str, step_index: int, memory: MemoryStores) -> Path:
    """Atomic write: write to .tmp then rename. Returns checkpoint path."""

def load_latest_checkpoint(session_id: str) -> dict | None:
    """Find latest checkpoint file for session_id, load and return."""
```

### Acceptance tests — `tests/unit/test_error_control.py`

```python
# Parser tests
def test_parser_handles_json_fence():
def test_parser_handles_trailing_comma():
def test_parser_handles_single_quoted_keys():
def test_parser_handles_truncated_json():
def test_parser_returns_none_on_unrecoverable():

# Quality gate tests
def test_quality_gate_fails_on_empty():
def test_quality_gate_fails_on_unparseable():
def test_quality_gate_detects_loop_at_threshold_3():
def test_quality_gate_passes_clean_input():

# Truncation tests
def test_truncation_asymmetric_formula():
    """text of 10000 chars, cap 4000 → head=3000, tail=1000."""
def test_truncation_passthrough_under_cap():

# Watchdog tests
def test_watchdog_returns_result_before_timeout():
def test_watchdog_returns_timeout_result_on_slow_fn():
def test_watchdog_never_raises():

# Sandbox tests
def test_sandbox_allows_pytest():
def test_sandbox_blocks_rm():
def test_sandbox_blocks_curl():

# Checkpoint tests
def test_checkpoint_saves_and_loads():
def test_checkpoint_atomic_write():
    """Simulate crash during write (partial .tmp); load still returns prior checkpoint."""
```

All 20 tests must pass.

### Commit
```
git add -A && git commit -m "phase-4: error control (parser, quality gate, truncation, watchdog, sandbox, checkpoint)"
```

---

## PHASE 5 — Bounded Tool Interface

**Goal:** Two primary tools (run_tests, py_compile_check) plus file tools (read, write-guarded, AST-gated edit). Tools return typed Pydantic objects, never raw strings.

### `src/framework/tools/compile_check.py`

```python
class CompileResult(BaseModel):
    ok: bool
    errors: list[str]           # each: "line N: <message>"
    file_path: str

def py_compile_check(code_or_path: str) -> CompileResult:
    """ast.parse + py_compile.compile. Returns typed result."""
```

### `src/framework/tools/test_runner.py`

```python
class TestResult(BaseModel):
    passed: bool
    total_tests: int
    failed_tests: list[str]
    error_message: str | None
    stdout: str                 # truncated
    stderr: str                 # truncated
    exit_code: int
    duration_ms: int

def run_tests(target_path: str, workspace: Path,
              timeout_s: int = 30) -> TestResult:
    """
    Runs pytest in sandboxed subprocess via safe_execute.
    Parses JSON output (pytest --json-report or --tb=short).
    Applies output truncation before returning.
    """
```

### `src/framework/tools/file_tools.py`

```python
class FileResult(BaseModel):
    ok: bool
    message: str
    content: str | None = None   # for read_file

def read_file(file_path: str, workspace: Path) -> FileResult:
    """Read file. Apply truncation(read_file cap). Return FileResult."""

def write_file(file_path: str, content: str, workspace: Path) -> FileResult:
    """
    WRITE GUARD: if file exists → return FileResult(ok=False, message=prescriptive_error).
    Prescriptive error includes exact edit_file call shape.
    """

def edit_file(file_path: str, old_string: str,
              new_string: str, workspace: Path) -> FileResult:
    """
    AST GATE:
    1. Read file.
    2. Check old_string exists exactly once (not zero, not twice).
    3. Replace.
    4. ast.parse the result.
    5. If parse fails → discard (restore original), return FileResult(ok=False, message=error+snippet).
    6. If parse passes → write to disk. Return FileResult(ok=True).
    """
```

### `src/framework/tools/search.py` (SWE-bench only)

```python
class CodeChunk(BaseModel):
    file: str
    line_start: int
    line_end: int
    text: str                   # truncated to 200 chars

def build_keyword_index(workspace: Path) -> dict:
    """Index all .py files by bigrams and unigrams."""

def search_codebase(query: str, index: dict, top_k: int = 3) -> list[CodeChunk]:
    """Keyword overlap scoring. Return top-k chunks."""
```

### Acceptance tests — `tests/unit/test_tools.py`

```python
def test_compile_check_passes_valid_python():
def test_compile_check_fails_syntax_error():
def test_compile_check_returns_line_number():

def test_run_tests_passes_correct_code(tmp_path):
    """Write a simple passing test file; run_tests returns passed=True."""
def test_run_tests_fails_wrong_code(tmp_path):
def test_run_tests_output_is_truncated():

def test_write_file_creates_new_file(tmp_path):
def test_write_file_refuses_existing_file(tmp_path):
def test_write_file_prescriptive_error_contains_edit_call(tmp_path):

def test_edit_file_replaces_exact_match(tmp_path):
def test_edit_file_fails_when_old_string_not_found(tmp_path):
def test_edit_file_fails_when_old_string_appears_twice(tmp_path):
def test_edit_file_ast_gate_rejects_syntax_error(tmp_path):
def test_edit_file_ast_gate_keeps_original_on_reject(tmp_path):

def test_search_codebase_bigram_scores_higher(tmp_path):
```

All 15 tests must pass.

### Commit
```
git add -A && git commit -m "phase-5: bounded tool interface (run_tests, compile_check, file tools, write-guard, AST-gate)"
```

---

## PHASE 6 — Decision Cycle

**Goal:** The per-LLM-call cycle: READ_CONTEXT → PROPOSE → SELF_CHECK → CORRECT → ACT → RECORD. This is the inner loop that every agent call goes through.

### `src/framework/control/self_check.py`

```python
def self_check(proposal: DecisionEntry,
               memory: MemoryStores,
               session_id: str) -> SelfCheckRecord:
    """
    Check 1: Schema validation — proposal fields valid?
    Check 2: Contradiction — proposal conflicts with last 10 Decision Log entries?
    Check 3: Scope violation — executor making plan_step? planner invoking tool?
    Check 4: Rationale present — rationale field is not empty?
    Returns SelfCheckRecord(verdict, issues).
    """
```

Contradiction detection rule: same `kind` + same `payload` key but different value compared to a prior committed decision → flag as contradiction. Keep it simple — exact field match, not semantic.

### `src/framework/control/cycle.py`

```python
class DecisionCycle:
    def __init__(self, slm: SLMClient, memory: MemoryStores,
                 wm_builder: WorkingMemoryBuilder,
                 error_control: ErrorControlBundle,
                 profile: ModelProfile): ...

    def run(self, session_id: str, agent_role: str,
            current_subtask: str, subtask_id: str,
            action_fn: Callable[[DecisionEntry], Any],
            max_retries: int = 3) -> CycleResult:
        """
        Step 1 READ_CONTEXT: build WorkingMemory
        Step 2 PROPOSE: call SLM, get raw text
        Step 3 quality gate: parse + quality check
        Step 4 SELF_CHECK: deterministic checks
        Step 5 CORRECT if needed: mutate prompt, retry (bounded)
        Step 6 ACT: call action_fn with validated proposal
        Step 7 RECORD: write DecisionEntry to Decision Log
        Returns CycleResult(decision, outcome, retry_count)
        """

    def _build_corrective_prompt(self, wm: WorkingMemory,
                                  issues: list[Issue],
                                  retry_count: int) -> list[dict]:
        """
        Prepend original prompt.
        Append each issue as a specific instruction.
        Restate violated constraint.
        Request strict JSON.
        """
```

### `src/framework/control/budget.py`

```python
class StepBudgetLimiter:
    def __init__(self, max_steps: int, max_retries: int): ...
    def check_steps(self, current: int) -> bool: ...     # True = ok to continue
    def check_retries(self, current: int) -> bool: ...
    def remaining(self, current: int) -> dict: ...
```

### Acceptance tests — `tests/unit/test_self_check.py`

```python
def test_self_check_passes_valid_proposal():
def test_self_check_fails_missing_rationale():
def test_self_check_fails_scope_violation_executor_plan():
def test_self_check_fails_scope_violation_planner_tool():
def test_self_check_detects_contradiction_same_key_different_value():
def test_self_check_no_contradiction_when_log_empty():
def test_self_check_no_contradiction_same_key_same_value():
```

```python
# tests/integration/test_decision_cycle.py  (uses mocked SLM client)

def test_cycle_completes_on_valid_proposal(mock_slm):
    """Mocked SLM returns valid JSON → cycle completes, decision recorded."""

def test_cycle_retries_on_schema_fail(mock_slm):
    """First SLM call returns invalid JSON → parser fails → corrective prompt → retry → success."""

def test_cycle_marks_exhausted_after_max_retries(mock_slm):
    """SLM always returns invalid → after max_retries → CycleResult.exhausted=True."""

def test_cycle_records_decision_in_log(mock_slm, memory):
    """After successful cycle → DecisionLog has exactly 1 new entry."""

def test_cycle_records_self_check_result(mock_slm, memory):
    """DecisionEntry in log has self_check.verdict == 'pass'."""

def test_budget_limiter_stops_cycle(mock_slm):
    """max_steps=1, step_count=1 → cycle returns budget_exceeded before calling SLM."""
```

All 13 tests must pass.

### Commit
```
git add -A && git commit -m "phase-6: decision cycle (READ→PROPOSE→SELF_CHECK→CORRECT→ACT→RECORD)"
```

---

## PHASE 7 — Workflow State Machine

**Goal:** LangGraph StateGraph with 7 states. Deterministic transitions. Progress Ledger. Verbal reflection on REVISE. Checkpointing via LangGraph.

### `src/framework/control/workflow.py`

```python
class WorkflowState(TypedDict):
    session_id: str
    goal: str
    hard_constraints: list[str]
    current_state: str
    active_subtask_id: str | None
    step_count: int
    retry_count: int
    loop_count: int
    max_steps: int
    max_retries: int
    last_evaluation: dict | None    # serialized EvaluationResult

def next_state(state: WorkflowState, memory: MemoryStores) -> str:
    """Pure function. All transition logic here. No SLM call."""

def _loop_detected(memory: MemoryStores, state: WorkflowState) -> bool:
    """Check last 5 Decision Log entries for same kind+hash appearing 3+ times."""
```

### `src/framework/control/ledger.py`

```python
class ProgressLedger(BaseModel):
    session_id: str
    step_index: int
    is_task_satisfied: bool
    is_in_loop: bool
    is_progress_being_made: bool
    steps_consumed: int
    budget_remaining: int

def build_progress_ledger(state: WorkflowState, memory: MemoryStores) -> ProgressLedger:
    """Called at every EVALUATE step. Written to State Store."""
```

### `src/framework/memory/reflection.py`

```python
REFLECTION_PROMPT = """Task: {original_goal}
Current subtask: {current_subtask}
Attempt {retry_count} failed.
Failure reason: {failure_reason}

In 2-3 sentences: what went wrong, and what specific change should the next attempt make?
Do not repeat what failed. Focus only on what to do differently."""

def write_reflection(slm: SLMClient, session_id: str, step_index: int,
                     original_goal: str, current_subtask: str,
                     retry_count: int, failure_reason: str,
                     memory: MemoryStores) -> str:
    """
    Call SLM with reflection prompt.
    Write result as DecisionEntry(kind='reflection', importance=1.0).
    Return reflection text.
    Capped at 3 reflections per subtask (from config).
    """
```

### `src/framework/orchestration/graph.py`

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver   # or RedisSaver

def build_graph(planner, executor, memory, config) -> CompiledGraph:
    builder = StateGraph(WorkflowState)
    builder.add_node("PLAN",     planner.plan_node)
    builder.add_node("DISPATCH", planner.dispatch_node)
    builder.add_node("EXECUTE",  executor.execute_node)
    builder.add_node("EVALUATE", evaluation_node)
    builder.add_node("REVISE",   revise_node)
    builder.add_node("ESCALATE", escalation_node)
    builder.set_entry_point("PLAN")
    builder.add_edge("PLAN",     "DISPATCH")
    builder.add_edge("DISPATCH", "EXECUTE")
    builder.add_edge("EXECUTE",  "EVALUATE")
    builder.add_conditional_edges("EVALUATE", next_state_router, {
        "DISPATCH":  "DISPATCH",
        "REVISE":    "REVISE",
        "DONE":      END,
        "ESCALATE":  "ESCALATE",
    })
    builder.add_edge("REVISE", "EXECUTE")
    checkpointer = SqliteSaver.from_conn_string(config.sqlite_path)
    return builder.compile(checkpointer=checkpointer)
```

### Acceptance tests — `tests/integration/test_workflow.py`

```python
def test_next_state_plan_returns_dispatch():
def test_next_state_evaluate_returns_done_when_tests_pass():
def test_next_state_evaluate_returns_revise_on_test_failure():
def test_next_state_evaluate_returns_escalate_when_retries_exhausted():
def test_next_state_revise_returns_execute():
def test_loop_detected_at_threshold_3():
def test_loop_not_detected_below_threshold():
def test_progress_ledger_built_correctly():
def test_graph_compiles_without_error():
def test_graph_checkpoint_saves_state():
def test_reflection_written_to_decision_log(mock_slm):
def test_reflection_capped_at_max_per_config(mock_slm):
```

All 12 tests must pass.

### Commit
```
git add -A && git commit -m "phase-7: workflow state machine (LangGraph, 7 states, ledger, reflection)"
```

---

## PHASE 8 — Agent Implementations

**Goal:** Planner and Executor agents. Each wraps the Decision Cycle with its role-specific logic. Typed message protocol between them.

### `src/framework/orchestration/messages.py`

```python
class DispatchMessage(BaseModel):
    session_id: str
    task_id: str
    subtask_description: str
    memory_slice_keys: list[str]
    step_budget: int
    hard_constraints: list[str]

class ReportMessage(BaseModel):
    session_id: str
    task_id: str
    outcome: Literal["success","failure","partial"]
    new_memory_refs: list[str]
    evidence_summary: str

class HandbackMessage(BaseModel):
    session_id: str
    task_id: str
    reason: str
    blocked_on: str

class TerminateMessage(BaseModel):
    session_id: str
    outcome: Literal["solved","max_steps_reached","unresolvable"]
    decision_refs: list[str]
    result_refs: list[str]
```

### `src/framework/orchestration/planner.py`

```python
class PlannerAgent:
    """
    plan_node(state) → WorkflowState:
      - Read task goal from state
      - Call Decision Cycle with role='planner', kind='plan_step'
      - Write sub-tasks to SubTaskRegistry
      - Return updated state

    dispatch_node(state) → WorkflowState:
      - Read ProgressLedger from State Store
      - Select next pending sub-task
      - Build DispatchMessage
      - Write to State Store (dispatch record)
      - Return updated state with active_subtask_id
    """
```

**Planner system prompt skeleton (from implementation spec §5.4):**
```
[ROLE]: You are the Planner agent. You decompose programming tasks into ordered,
verifiable sub-tasks. You do not write code. You do not invoke tools.
[GOAL]: {original_goal}
[CONSTRAINTS]: {hard_constraints}
[CURRENT TASK]: {current_subtask}
[CONTEXT]: {retrieved_items}
[PROGRESS]: {progress_ledger_summary}
---
Decompose the above into sub-tasks. Each sub-task must be:
- Atomic (achievable in one Executor pass)
- Verifiable (has a clear done criterion)
- Non-overlapping

Output a single JSON Decision object. rationale is mandatory.
[FORMAT]: {decision_schema}
```

### `src/framework/orchestration/executor.py`

```python
class ExecutorAgent:
    """
    execute_node(state) → WorkflowState:
      - Read DispatchMessage from State Store
      - Load sub-task description
      - Call Decision Cycle with role='executor'
      - For each cycle iteration:
          - If kind == 'code_edit' → call edit_file or write_file
          - If kind == 'tool_call' → call run_tests or py_compile_check
          - If kind == 'handoff' → emit HandbackMessage
      - Write ReportMessage to State Store
      - Return updated state
    """
```

**Executor system prompt skeleton:**
```
[ROLE]: You are the Executor agent. You carry out exactly one assigned sub-task.
You write and edit Python code. You invoke run_tests and py_compile_check.
You do not create new sub-tasks. You do not change the goal.
[GOAL]: {original_goal}
[CONSTRAINTS]: {hard_constraints}
[CURRENT TASK]: {current_subtask}
[CONTEXT]: {retrieved_items}
[LAST ERROR]: {last_error}
[GUIDANCE]: {skill_card}
---
Carry out the sub-task above. Output a single JSON Decision object.
rationale is mandatory. kind must be one of: code_edit, tool_call, handoff.
[FORMAT]: {decision_schema}
```

### Acceptance tests — `tests/integration/test_decision_cycle.py` (additions)

```python
def test_planner_writes_subtasks_to_registry(mock_slm, memory):
def test_planner_dispatch_selects_pending_subtask(mock_slm, memory):
def test_executor_calls_tool_on_tool_call_decision(mock_slm, memory, tmp_path):
def test_executor_calls_edit_file_on_code_edit(mock_slm, memory, tmp_path):
def test_executor_emits_handback_when_out_of_scope(mock_slm, memory):
def test_planner_receives_report_after_executor_done(mock_slm, memory):
```

All 6 new tests must pass (total integration tests: 19).

### Commit
```
git add -A && git commit -m "phase-8: planner and executor agents, typed message protocol"
```

---

## PHASE 9 — Integration: Full Session End-to-End

**Goal:** Run a complete session from task input to DONE or ESCALATE. Must work on at least 3 real HumanEval-style tasks without crashing.

> ⚠️ **This phase requires `OPENROUTER_API_KEY` to be set in `.env`. The agent must check this before running and print a clear error if missing.**

### Integration test — `tests/e2e/test_full_session.py`

```python
# Three synthetic tasks (not from benchmark — hardcoded for reproducibility)

TASK_1 = {
    "goal": "Write a Python function add(a, b) that returns a + b.",
    "constraints": ["Must be named exactly 'add'", "Must handle integers and floats"],
    "test_code": "assert add(1, 2) == 3\nassert add(1.5, 2.5) == 4.0"
}

TASK_2 = {
    "goal": "Fix the bug in the provided function: def multiply(a, b): return a - b",
    "constraints": ["Must not change the function name", "Fix only the operator"],
    "test_code": "assert multiply(3, 4) == 12"
}

TASK_3 = {
    "goal": "Write a Python function is_palindrome(s) that returns True if s is a palindrome.",
    "constraints": ["Case-insensitive", "Ignore spaces"],
    "test_code": "assert is_palindrome('racecar')\nassert is_palindrome('Race Car')\nassert not is_palindrome('hello')"
}

def test_full_session_task_1():
    """Session reaches DONE. TestResult.passed=True. Decision Log has entries."""

def test_full_session_task_2():
    """Session reaches DONE. Executor correctly fixes the bug."""

def test_full_session_task_3():
    """Session reaches DONE. Generated function passes all 3 test assertions."""

def test_decision_log_has_entries_after_session():
    """After any completed session, Decision Log is non-empty."""

def test_state_store_has_snapshots_after_session():
    """State Store has at least 2 snapshots (initial + final)."""

def test_checkpoint_exists_after_session():
    """Checkpoint file exists in CHECKPOINT_DIR after session."""
```

All 6 e2e tests must pass with real API calls. Mark with `@pytest.mark.e2e` so they can be skipped in CI without an API key.

### Smoke test script — `scripts/smoke_test.py`

```bash
python scripts/smoke_test.py
# Runs TASK_1 above, prints Decision Log, prints outcome.
# Must complete in < 5 minutes.
# Must print "OUTCOME: solved" at the end.
```

### Commit
```
git add -A && git commit -m "phase-9: e2e integration, smoke test, full session verified"
```

---

## PHASE 10 — Evaluation Harness

**Goal:** Adapters for HumanEval, MBPP, and SWE-bench. SR and CER metrics. The harness runs one config on one dataset and writes results to JSONL.

### `eval/datasets/humaneval_adapter.py`

```python
class HumanEvalTask(BaseModel):
    task_id: str
    prompt: str             # function signature + docstring
    test_code: str          # hidden tests
    entry_point: str        # function name

def load_humaneval(n: int = 50, seed: int = 42) -> list[HumanEvalTask]:
    """Load from HuggingFace datasets. Sample n tasks. Stratified by difficulty if possible."""
```

### `eval/datasets/mbpp_adapter.py`

Same structure. MBPP tasks have `text` (problem description) and `test_list` (assertions).

### `eval/metrics/sr.py` and `eval/metrics/cer.py`

```python
def compute_sr(results: list[RunResult]) -> float:
    """SR = solved / total * 100"""

def compute_cer(results: list[RunResult]) -> float:
    """CER = failed_interactions / total_interactions * 100"""

class RunResult(BaseModel):
    task_id: str
    solved: bool
    outcome: str            # "solved" | "max_steps_reached" | "unresolvable"
    interaction_count: int
    step_count: int
    retry_count: int
    trace_path: str
```

### `eval/run_eval.py`

```python
def run_eval(config_name: str,        # "A" | "B" | "C" | "D"
             dataset_name: str,       # "humaneval" | "mbpp" | "swebench"
             n: int | None = None,
             seed: int = 42) -> dict:
    """
    Loads config from configs/eval.yaml.
    Iterates tasks.
    Writes results to traces/{config}_{dataset}_{timestamp}.jsonl.
    Returns {"sr": float, "cer": float, "n": int, "config": str}.
    """
```

### Acceptance tests — `tests/unit/` (metrics only, no real runs)

```python
def test_sr_all_solved():
    """10 tasks, all solved → SR = 100.0"""
def test_sr_none_solved():
    """10 tasks, none solved → SR = 0.0"""
def test_cer_all_failed():
    """10 tasks, all failed → CER = 100.0"""
def test_run_result_schema_valid():
def test_eval_config_loads_from_yaml():
```

### Commit
```
git add -A && git commit -m "phase-10: evaluation harness (HumanEval, MBPP adapters, SR, CER metrics)"
```

---

## PHASE 11 — Ablation Runner

**Goal:** Run all four configurations (A/B/C/D) on the same task sample. Produce a comparison table. This is the core thesis evidence.

### `eval/scenarios/ablation.py`

```python
def run_ablation(dataset: str, n: int = 50, seed: int = 42) -> AblationResult:
    """
    Runs configs A, B, C, D in sequence on the same task sample.
    Writes per-config JSONL traces.
    Returns AblationResult with SR and CER for each config.
    Prints comparison table to stdout.
    """

class AblationResult(BaseModel):
    dataset: str
    n_tasks: int
    configs: dict[str, ConfigResult]    # "A" → {sr, cer}
    timestamp: str

def print_comparison_table(result: AblationResult) -> None:
    """
    Prints:
    Config | SR (%) | CER (%) | Memory | Control | Error Control
    A      | ...    | ...     | No     | No      | No
    B      | ...    | ...     | Yes    | No      | No
    C      | ...    | ...     | No     | Yes     | No
    D      | ...    | ...     | Yes    | Yes     | Yes
    """
```

### `eval/scenarios/agent_count.py`

```python
def run_agent_count_experiment(dataset: str = "swebench",
                                n: int = 30, seed: int = 42) -> dict:
    """
    Runs config D with:
    - 1 agent (Executor only, no Planner)
    - 2 agents (Planner + Executor)
    Reports CER for each.
    """
```

### Commit
```
git add -A && git commit -m "phase-11: ablation runner (configs A/B/C/D, comparison table)"
```

---

## PHASE 12 — Qualitative Trace Analysis Tools

**Goal:** Simple scripts to inspect Decision Log traces for the qualitative evaluation criteria.

### `scripts/analyze_traces.py`

```python
# CLI tool: python scripts/analyze_traces.py --trace traces/D_humaneval_*.jsonl

def count_self_check_failures(trace_path: str) -> dict:
    """Count schema_violation, contradiction, scope_violation per session."""

def count_contradictions(trace_path: str) -> int:
    """Count Decision Log entries where self_check has contradiction issues."""

def extract_retry_curves(trace_path: str) -> list[dict]:
    """Per session: {session_id, subtask_id, attempts} for retry analysis."""

def check_behavioral_interpretability(trace_path: str, session_id: str) -> None:
    """Print Decision Log + State snapshots for one session in readable format."""
```

### `scripts/generate_report.py`

```python
# Generates thesis_evaluation_report.md from all trace files
# Includes: SR/CER table, contradiction counts, retry curves, sample traces
```

### Final acceptance — `tests/e2e/test_humaneval_sample.py`

```python
@pytest.mark.e2e
def test_humaneval_20_tasks_config_D():
    """
    Run config D on 20 HumanEval tasks.
    SR must be > 40% (model capability floor, not framework floor).
    CER must be < 60%.
    All traces written to JSONL.
    """

@pytest.mark.e2e
def test_ablation_d_beats_a_on_humaneval():
    """
    Run configs A and D on same 20 HumanEval tasks.
    D.SR > A.SR (at least 5 percentage points better).
    D.CER < A.CER.
    """
```

### Final commit

```
git add -A && git commit -m "phase-12: qualitative trace analysis, evaluation report generator"
git tag v1.0-thesis-prototype
```

---

## Test Coverage Summary

| Phase | Test type | Count | Gate |
|---|---|---|---|
| 0 | Smoke | 4 | All pass |
| 1 | Unit (mocked) | 6 | All pass |
| 2 | Unit | 10 | All pass |
| 3 | Unit | 6 | All pass |
| 4 | Unit | 20 | All pass |
| 5 | Unit | 15 | All pass |
| 6 | Unit + Integration | 13 | All pass |
| 7 | Integration | 12 | All pass |
| 8 | Integration | 6 | All pass |
| 9 | E2E (real API) | 6 | All pass |
| 10 | Unit (metrics) | 5 | All pass |
| 11 | (output validation) | — | Table printed |
| 12 | E2E (real API) | 2 | SR>40%, D>A |

**Total tests: ~105.** Run unit tests anytime (`pytest tests/unit`). Run integration tests without API key (`pytest tests/integration`). Run E2E only with API key set (`pytest tests/e2e -m e2e`).

---

## One-Command Test Gates Per Phase

```bash
# Before marking any phase DONE, run its gate:
PHASE 0:  pytest tests/ --collect-only
PHASE 1:  pytest tests/unit/test_slm_client.py
PHASE 2:  pytest tests/unit/test_memory_stores.py
PHASE 3:  pytest tests/unit/test_retrieval.py
PHASE 4:  pytest tests/unit/test_error_control.py
PHASE 5:  pytest tests/unit/test_tools.py
PHASE 6:  pytest tests/unit/test_self_check.py tests/integration/test_decision_cycle.py
PHASE 7:  pytest tests/integration/test_workflow.py
PHASE 8:  pytest tests/integration/  # all integration tests
PHASE 9:  pytest tests/e2e/test_full_session.py -m e2e
PHASE 10: pytest tests/unit/   # all unit tests must still pass
PHASE 11: python eval/scenarios/ablation.py --dry-run
PHASE 12: pytest tests/e2e/ -m e2e
```
