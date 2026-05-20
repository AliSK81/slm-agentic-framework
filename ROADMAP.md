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
PHASE 13 → Run integrity: API probe retry + run-level quality gate
PHASE 14 → Eval CLI: single-task rerun + per-run reproducibility manifest
PHASE 15 → Measurable difficulty slices (HumanEval hard-only + stratified)
PHASE 16 → Controlled multi-step scenarios (interaction-length sweep)        [RQ3]
PHASE 17 → Reflection wired into REVISE                                      [RQ2/RQ3]
PHASE 18 → True-SLM profile + provider replication                          [REQUIRES_USER_INPUT]
PHASE 19 → Valid full ablation A–D (multi-seed, manifested)                  [REQUIRES_USER_INPUT]
PHASE 20 → MBPP ablation + traces                                           [REQUIRES_USER_INPUT]
PHASE 21 → SWE-bench Lite Docker runner                                      [REQUIRES_USER_INPUT]
PHASE 22 → Agent-count experiment (1 vs 2 agents, CER focus)   [RQ3]         [REQUIRES_USER_INPUT]
PHASE 23 → Decision-log JSONL export + checkpoint↔task_id linking            [RQ1/RQ2]
PHASE 24 → Qualitative metrics (coherence / interpretability / stability)    [RQ1/RQ2]
PHASE 25 → LangGraph production path OR documented deprecation               [REQUIRES_USER_INPUT]
PHASE 26 → Cost / latency / token accounting per session
PHASE 27 → Reproducibility bundle + results-chapter automation (curated only)
PHASE 28 → Hardening (registry error path, parser newline, ThinkingBudget tests)
PHASE 29 → Retrieval-mechanism ablation (keyword vs semantic) + Redis backend  [RQ1] [REQUIRES_USER_INPUT]
PHASE 30 → Discriminative hard slice (break the n=10 ceiling effect)        [RQ2]
PHASE 31 → Live multi-seed A–D ablation, DeepSeek (mean ± 95% CI)           [RQ2] [REQUIRES_USER_INPUT]
PHASE 32 → True-SLM live matrix (Qwen-7B + Devstral via OpenRouter)         [RQ2] [REQUIRES_USER_INPUT]
PHASE 33 → Keyword vs semantic retrieval live comparison                    [RQ1] [REQUIRES_USER_INPUT]
PHASE 34 → Efficiency chapter: SLM-vs-LLM cost/latency/token table          [REQUIRES_USER_INPUT]
PHASE 35 → MBPP full ablation n=50                                          [REQUIRES_USER_INPUT]
PHASE 36 → RQ3 live evidence: interaction-length + agent-count CER sweeps    [RQ3] [REQUIRES_USER_INPUT]
PHASE 37 → SWE-bench Lite pilot (5–10 instances)                            [REQUIRES_USER_INPUT]
PHASE 38 → Qualitative metrics + failure taxonomy on cited runs             [RQ1/RQ2]
PHASE 39 → Thesis tables & figures automation (curated-only, LaTeX)
PHASE 40 → Documentation pass + zipped reproducibility package
PHASE 41 → E2E regression smoke + optional Redis pilot                      [REQUIRES_USER_INPUT optional]
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

## Phase Overview — Phases 13+

> **Context for the implementing agent:** Phases 0–12 are DONE. The production path is the imperative
> `run_full_session()` loop in `orchestration/session.py` (LangGraph is off this path), and the active
> provider is **DeepSeek `deepseek-v4-flash`**, not the OpenRouter Qwen/Devstral spec in Phases 0–8.
> The headline thesis result is currently **not demonstrable**: on the canonical HumanEval-20 slice
> `A = D = 100% SR`, and the B/C runs are invalid (`interaction_count = 0`, infrastructure failure, not a
> framework comparison). Phases 13–29 exist to (a) make the A/B/C/D ablation *valid and measurable*,
> (b) produce the MBPP/SWE/agent-count evidence the thesis promises, and (c) close the production gaps
> the thesis claims but does not run. Each phase ties to **RQ1 (memory)**, **RQ2 (decision accuracy)**,
> or **RQ3 (cumulative error vs. agent/interaction count)** only where the codebase supports it.

Each phase keeps the same contract: **Goal → Tasks → Acceptance tests → Commit**. Architecture rules are
unchanged: all data crossing module boundaries is **typed Pydantic v2**; every LLM call goes through the
**Decision Cycle** (`control/cycle.py`) or the bounded `SLMClient`; all FSM transitions stay **pure Python**
(`next_state` takes no LLM call); **no secrets** are ever written to the repo (manifests record provider/model
ids and git SHA, never keys).

> Phases that need real API spend, Docker, or an advisor decision are marked `[REQUIRES_USER_INPUT]`. Their
> CI-checkable acceptance gate is always a `--dry-run` / structural test that validates wiring **without**
> spending budget; the real run is a separate, explicitly-flagged evidence step. **Do not fabricate run
> numbers** — ablation gates assert *valid runs were produced and tabulated*, never a specific SR/CER margin.

---

## PHASE 13 — Run Integrity: API Probe Retry + Run-Level Quality Gate

**Goal:** Eliminate the zero-interaction failure mode that invalidated every B/C run (handoff §7.2, §7.3).
A run where tasks did no work must be flagged `INVALID`, not silently scored `SR=0`.

### Tasks

- `src/framework/orchestration/session.py` — rewrite `validate_slm_api_key()` to retry the `probe_client()`
  call on transient errors (`timeout`, `http_error`, `http_5xx`, SSL/connection) with exponential backoff
  (3 attempts, base 2 s). Return a typed result; on exhaustion raise `ProbeFailedError` *before* the task
  loop so no task records `interaction_count = 0`.

```python
class ProbeResult(BaseModel):
    ok: bool
    attempts: int
    error: str | None

def validate_slm_api_key(max_attempts: int = 3) -> ProbeResult: ...
```

- `eval/run_quality.py` (new) — a deterministic, no-LLM run-level gate over an aggregate JSONL:

```python
class RunQuality(BaseModel):
    run_path: str
    n_tasks: int
    zero_interaction_tasks: int
    valid: bool                 # False if zero_interaction fraction > threshold
    reason: str | None

def assess_run(run_path: str, max_zero_ix_fraction: float = 0.10) -> RunQuality:
    """A run is INVALID if > max_zero_ix_fraction of tasks have interaction_count == 0."""
```

- `eval/run_eval.py` — call `assess_run()` after writing the aggregate JSONL; stamp `"run_valid": bool`
  and `"run_invalid_reason"` into a sidecar `traces/{run}.quality.json`. Print `RUN INVALID: <reason>` to
  stderr and exit non-zero when invalid so batch scripts stop instead of accumulating junk.

### Acceptance tests — `tests/unit/test_run_quality.py`, `tests/unit/test_api_probe_retry.py`

```python
def test_assess_run_flags_all_zero_interaction_as_invalid():
def test_assess_run_passes_when_all_tasks_interacted():
def test_assess_run_threshold_boundary():            # exactly 10% zero-ix → still valid
def test_probe_retries_on_transient_error_then_succeeds(mock_probe):
def test_probe_raises_after_max_attempts(mock_probe): # ProbeFailedError, loop never starts
def test_probe_does_not_retry_on_missing_api_key(mock_probe):  # config error, fail fast
```

### Commit
```
git add -A && git commit -m "phase-13: run integrity (probe retry, run-level zero-interaction quality gate)"
```

---

## PHASE 14 — Eval CLI: Single-Task Rerun + Per-Run Reproducibility Manifest

**Goal:** Make every run reproducible and cheaply re-runnable. Adds `--task-id` (the missing flag noted in
PROGRESS issues) and writes a manifest capturing exactly how a run was produced — no secrets.

### Tasks

- `eval/manifest.py` (new):

```python
class RunManifest(BaseModel):
    run_id: str
    config: str                 # "A" | "B" | "C" | "D"
    dataset: str
    n: int
    seed: int
    provider: str               # from configs/models.yaml active_provider
    planner_profile: str
    executor_profile: str
    git_sha: str                # subprocess: git rev-parse HEAD
    task_ids: list[str]
    ablation_flags: dict        # {memory, control, error_control}
    created_at: datetime
    # NEVER include API keys or env secrets

def write_manifest(run_id: str, **kw) -> Path:   # traces/{run_id}.manifest.json
```

- `eval/run_eval.py` — add `--task-id` (repeatable) that bypasses sampling and runs exactly the named
  task(s) via the existing `_run_single_task`; always emit a `RunManifest` next to the aggregate JSONL.
- Replace the ad-hoc single-task rerun script referenced in PROGRESS with this first-class CLI path.

### Acceptance tests — `tests/unit/test_manifest.py`

```python
def test_manifest_written_with_git_sha_and_no_secrets():   # asserts no "key"/"token" values present
def test_manifest_records_ablation_flags_for_config_D():
def test_run_eval_task_id_runs_only_named_task(monkeypatch):
```

CLI gate (no API key needed):
```
python -m eval.run_eval --config D --dataset humaneval --task-id HumanEval/0 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-14: eval CLI --task-id rerun + per-run reproducibility manifest"
```

---

## PHASE 15 — Measurable Difficulty Slices (HumanEval Hard-Only + Stratified)

**Goal:** Create a task slice on which config A (no memory/control/error-control) does **not** trivially score
100%, so the framework's contribution becomes measurable. This is the precondition for any valid D>A claim.

### Tasks

- `eval/datasets/humaneval_adapter.py` — add a **deterministic** difficulty label (no LLM) so the slice is
  reproducible:

```python
def difficulty_of(task: HumanEvalTask) -> Literal["easy","medium","hard"]:
    """
    Deterministic heuristic from the prompt itself:
      - hard   if prompt_loc > 12 OR n_assertions >= 8 OR contains nested-loop / DP keywords
      - medium if prompt_loc in 6..12 OR n_assertions in 4..7
      - easy   otherwise
    Plus an explicit curated override list configs/humaneval_hard_ids.txt.
    """

def load_humaneval(n=50, seed=42, difficulty: str | None = None) -> list[HumanEvalTask]:
    """difficulty='hard' returns only hard tasks; None keeps the existing stratified behaviour."""
```

- `configs/eval.yaml` — add a named dataset alias `humaneval_hard: {difficulty: hard, sample_size: 30, seed: 42}`
  and keep `humaneval` (stratified) unchanged.
- `configs/humaneval_hard_ids.txt` — curated, version-controlled list of HumanEval ids used as the canonical
  hard slice (overrides the heuristic so the thesis slice is frozen and citable).

### Acceptance tests — `tests/unit/test_difficulty_slices.py`

```python
def test_difficulty_is_deterministic_for_fixed_task():
def test_hard_slice_contains_only_hard_tasks():
def test_curated_hard_ids_override_heuristic():
def test_stratified_default_unchanged():           # regression: existing humaneval behaviour intact
```

### Commit
```
git add -A && git commit -m "phase-15: deterministic difficulty labels + curated HumanEval hard slice"
```

---

## PHASE 16 — Controlled Multi-Step Scenarios (Interaction-Length Sweep) [RQ3]

**Goal:** Directly answer **RQ3** — how cumulative error (CER) scales with the number of interactions.
Build synthetic tasks whose required interaction length is a controlled variable, so CER can be plotted
against interaction count. This is where memory + control are expected to keep config D coherent while A
degrades.

### Tasks

- `eval/datasets/synthetic_multistep.py` (new) — generate parametric tasks with a known minimum number of
  dependent edits/sub-tasks `L` (e.g. build module A, then B depending on A, then C calling both; hidden
  tests check the full chain). Each task is fully deterministic given `(L, seed)`.

```python
class MultiStepTask(BaseModel):
    task_id: str
    required_steps: int          # L: controlled interaction length
    prompt: str
    test_code: str
    entry_point: str

def generate_multistep(levels: list[int] = [2,4,6,8], per_level: int = 5, seed: int = 42) -> list[MultiStepTask]:
```

- `eval/scenarios/interaction_length.py` (new):

```python
def run_interaction_length(config: str, levels: list[int], seed: int = 42) -> dict:
    """
    For each L, run config on the L-step tasks via run_full_session.
    Returns {L: {sr, cer, mean_interactions}} and writes a manifested JSONL per L.
    Pure measurement — no claim asserted here.
    """
```

- `--dry-run` builds the task set and validates schemas/test compilation without calling the API.

### Acceptance tests — `tests/unit/test_interaction_length.py`

```python
def test_generated_tasks_are_deterministic():
def test_required_steps_monotonic_with_level():
def test_generated_test_code_compiles():           # py_compile_check on each test_code
def test_run_interaction_length_dry_run_builds_all_levels():
```

CLI gate:
```
python -m eval.scenarios.interaction_length --config D --levels 2,4,6,8 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-16: controlled multi-step scenarios for CER-vs-interaction-length (RQ3)"
```

---

## PHASE 17 — Reflection Wired into REVISE [RQ2/RQ3]

**Goal:** Make the verbal-reflection mechanism (spec'd in `memory/reflection.py` but **never called** in
production — handoff §3, §7.4) actually run on REVISE, so config D exercises error control on retries.
Reflection is part of the RQ2/RQ3 contribution and currently contributes nothing in real runs.

### Tasks

- `src/framework/orchestration/session.py` — on every REVISE transition (both the `control=True` `next_state`
  REVISE path and the simple fallback REVISE), call `write_reflection(...)` and feed the returned text into
  the next Decision Cycle as `last_error`/guidance for the retried subtask. Respect the existing
  `max_reflections_per_subtask` cap from `configs/memory.yaml`.
- Gate reflection behind the **error_control** ablation flag so configs A/C (no error control) do *not* reflect
  — this keeps the ablation honest (reflection is a D-only mechanism).
- The reflection call is a single bounded `SLMClient` call recorded as `DecisionEntry(kind="reflection",
  importance=1.0)`; **no** new FSM transition and **no** LLM inside `next_state`.

### Acceptance tests — `tests/integration/test_reflection_revise.py` (mocked SLM)

```python
def test_reflection_called_on_revise_when_error_control_on(mock_slm, memory):
def test_reflection_not_called_when_error_control_off(mock_slm, memory):   # config A/C
def test_reflection_capped_per_subtask(mock_slm, memory):
def test_reflection_text_feeds_next_attempt_as_guidance(mock_slm, memory):
def test_reflection_recorded_as_decision_entry(mock_slm, memory):
```

### Commit
```
git add -A && git commit -m "phase-17: wire write_reflection into REVISE (error_control-gated)"
```

---

## PHASE 18 — True-SLM Profile + Provider Replication [REQUIRES_USER_INPUT]

**Goal:** Protect the central thesis claim ("acceptable performance **without relying on LLMs**"). Production
ran DeepSeek `deepseek-v4-flash`, which is not clearly an SLM under the thesis's <30B framing (handoff §1).
Add and verify a genuine open-SLM configuration (OpenRouter Qwen2.5-Coder-7B planner + Devstral-Small executor,
the original Phase-0 spec) so the headline ablation can be reported on a true SLM.

> `[REQUIRES_USER_INPUT]` — needs an `OPENROUTER_API_KEY` with budget and confirmation of which model ids the
> committee accepts as "small". The agent must **not** create accounts or write keys to the repo; the user
> provides the key in `.env`.

### Tasks

- `configs/models.yaml` — add/restore verified profiles `qwen2.5-coder-7b-instruct` (point to the **7B** id, not
  the 32B id the handoff flagged) and `devstral-small`, plus a provider block `openrouter`. Add a named bundle
  `slm_small` (planner=Qwen-7B, executor=Devstral-Small) selectable via env `PLANNER_PROFILE`/`EXECUTOR_PROFILE`.
- `src/framework/slm/registry.py` — ensure `client_for_role` resolves the bundle and surfaces a clear error if a
  profile id is missing (see also Phase 28).
- `scripts/smoke_test.py` — accept `--bundle slm_small`; the smoke task (TASK_1) must reach `OUTCOME: solved`
  on the SLM bundle within 5 minutes.

### Acceptance tests — `tests/unit/test_slm_profiles.py` (no API), plus a marked e2e

```python
def test_slm_small_bundle_loads_two_distinct_profiles():
def test_qwen_profile_points_to_7b_id():            # regression on the handoff's 32B bug
def test_provider_block_resolves_openrouter_base_url():
```

Evidence step (needs key/budget):
```
pytest tests/e2e/test_full_session.py -m e2e            # run with PLANNER_PROFILE/EXECUTOR_PROFILE=slm_small
python scripts/smoke_test.py --bundle slm_small         # must print OUTCOME: solved
```

### Commit
```
git add -A && git commit -m "phase-18: verified true-SLM bundle (Qwen-7B + Devstral-Small) for thesis claim"
```

---

## PHASE 19 — Valid Full Ablation A–D (Multi-Seed, Manifested) [REQUIRES_USER_INPUT]

**Goal:** Produce the thesis's core evidence: a *valid* A/B/C/D comparison on a *measurable* slice
(Phase-15 hard HumanEval + Phase-16 multi-step), across multiple seeds, with manifests and the Phase-13
quality gate enforced. Replaces the broken A=D=100% / invalid-B/C situation.

> `[REQUIRES_USER_INPUT]` — API budget. Estimate cost before running: 4 configs × `n` × `seeds` sessions.

### Tasks

- `eval/scenarios/ablation.py` — add `--seeds 41,42,43`, `--dataset humaneval_hard|multistep`, and a
  `--profile-bundle` pass-through. For each `(config, seed)` write a manifested JSONL and run the Phase-13
  quality gate; **abort the whole ablation** if any run is INVALID (no silent junk).
- Extend `AblationResult` with per-config, per-seed `mean`/`std` of SR and CER and a `n_valid_tasks` count.
- `print_comparison_table()` adds `n_valid`, `SR mean±std`, `CER mean±std`, and the feature columns
  (Memory/Control/ErrorControl) already present.

### Acceptance tests

CLI gate (no spend — validates wiring, sampling, manifests, table formatting on stub results):
```
python -m eval.scenarios.ablation --dataset humaneval_hard --seeds 41,42,43 --dry-run
```

`tests/unit/test_ablation_runner.py` (extend):
```python
def test_ablation_aborts_on_invalid_run():
def test_ablation_aggregates_mean_std_across_seeds():
def test_comparison_table_has_feature_and_validity_columns():
```

Honest evidence test — **skips, never fails**, so a null result is documented not faked:
```python
@pytest.mark.e2e
def test_ablation_d_geq_a_on_hard_slice():
    """Run A and D on the hard slice. If D.SR >= A.SR + 5pp AND D.CER < A.CER → pass.
       Otherwise pytest.skip with the observed numbers (record, do not assert a fabricated win)."""
```

### Commit
```
git add -A && git commit -m "phase-19: valid multi-seed A-D ablation on measurable slices + manifests"
```

---

## PHASE 20 — MBPP Ablation + Traces [REQUIRES_USER_INPUT]

**Goal:** Deliver the MBPP evidence the thesis methodology promises (handoff §7.5: code ready, no API results).

> `[REQUIRES_USER_INPUT]` — API budget.

### Tasks

- `eval/datasets/mbpp_adapter.py` — confirm the sanitized MBPP load (`text` + `test_list`) maps cleanly to the
  `run_full_session` task shape; add the same deterministic `difficulty_of` heuristic as Phase 15.
- Run A–D on `mbpp` (n=50, seed=42) through the Phase-19 ablation path; produce manifested JSONL + per-task rows.
- Confirm the Phase-13 quality gate passes (no zero-interaction MBPP runs).

### Acceptance tests

```python
# tests/unit/test_eval_metrics.py / test_eval_paths.py (extend)
def test_mbpp_task_maps_to_session_shape():
def test_mbpp_test_list_compiles_to_pytest():
```

CLI gate (no spend):
```
python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run
```

Evidence step (needs budget):
```
python -m eval.scenarios.ablation --dataset mbpp --seeds 42 --n 50
```

### Commit
```
git add -A && git commit -m "phase-20: MBPP A-D ablation runs + traces"
```

---

## PHASE 21 — SWE-bench Lite Docker Runner [REQUIRES_USER_INPUT]

**Goal:** Replace the SWE-bench placeholder (`test_code = "assert False  # placeholder"`, handoff §4 Phase 10)
with a real per-instance Docker harness, so SWE-bench results reflect actual repository repair.

> `[REQUIRES_USER_INPUT]` — needs Docker available on the host **and** API budget. The agent must not install
> Docker or download untrusted images without the user enabling it.

### Tasks

- `eval/datasets/swebench_adapter.py` — load SWE-bench **lite**, materialize each instance's repo at the base
  commit into a workspace, and expose the gold `FAIL_TO_PASS` / `PASS_TO_PASS` test ids.
- `eval/swe_docker.py` (new) — run the instance's test command inside the official SWE-bench image via the
  Phase-4 sandbox `safe_execute` (allow-list extended with `docker`), parse pass/fail, return a typed
  `TestResult`. Hard timeout per instance; never raise.
- `configs/eval.yaml` — `swebench.docker_required: true`; the adapter raises a clear, skippable error if Docker
  is absent so CI without Docker degrades to skip, not failure.

### Acceptance tests — `tests/unit/test_swebench_docker.py`

```python
def test_swebench_instance_materializes_repo(tmp_path):     # mocked git, no network
def test_swe_docker_skips_cleanly_when_docker_absent(monkeypatch):
def test_swe_result_is_typed_testresult():
```

CLI gate (structural; Docker run is the evidence step):
```
python -m eval.run_eval --config D --dataset swebench --n 1 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-21: SWE-bench lite Docker runner (replaces placeholder tests)"
```

---

## PHASE 22 — Agent-Count Experiment (1 vs 2 Agents, CER Focus) [RQ3] [REQUIRES_USER_INPUT]

**Goal:** Answer the second half of **RQ3** — how the *number of agents* affects cumulative error. Run the
existing `agent_count.py` (Executor-only vs Planner+Executor) on real API, which the handoff notes has never
been run with live calls (§7.5).

> `[REQUIRES_USER_INPUT]` — API budget.

### Tasks

- `eval/scenarios/agent_count.py` — parameterize over the Phase-16 multi-step slice (where coordination load is
  real) and over seeds; for each (`planner_enabled` ∈ {False, True}) report SR, **CER**, mean interactions, and
  contradiction count (from Phase-23 decision logs once available). Write manifested JSONL.
- Ensure the 1-agent path still registers a root subtask so `interaction_count > 0` (guards against the
  zero-interaction artifact).

### Acceptance tests — extend `tests/unit/test_ablation_runner.py`

```python
def test_agent_count_one_agent_disables_planner():
def test_agent_count_two_agent_enables_planner():
def test_agent_count_reports_cer_per_arm():
```

CLI gate:
```
python -m eval.scenarios.agent_count --dataset multistep --dry-run
```

### Commit
```
git add -A && git commit -m "phase-22: agent-count experiment (1 vs 2 agents) CER measurement (RQ3)"
```

---

## PHASE 23 — Decision-Log JSONL Export + Checkpoint↔task_id Linking [RQ1/RQ2]

**Goal:** Fix the qualitative-analysis blocker (handoff §7.6): traces store only `RunResult` summaries in JSONL
while full decision logs live in `traces/checkpoints/*.json` keyed by `sess-*` ids that often don't match
`HumanEval/N`. Without a clean decision stream, RQ1/RQ2 qualitative claims can't be substantiated.

### Tasks

- `src/framework/orchestration/session.py` — alongside the `RunResult` row, stream each committed
  `DecisionEntry` to `traces/decisions/{config}_{dataset}_{run_id}.jsonl`, every line tagged with
  `task_id`, `session_id`, `step_index`, `kind`, `self_check.verdict`.
- Add a stable `task_id ↔ session_id` map written into the run manifest (Phase 14) so checkpoints, decision
  JSONL, and `RunResult` rows all join on `task_id`.
- `scripts/analyze_traces.py` — read decisions from the new JSONL (not only checkpoints); `check_behavioral_
  interpretability(task_id)` resolves via the manifest map.

### Acceptance tests — `tests/unit/test_decision_jsonl.py`, extend `tests/unit/test_analyze_traces.py`

```python
def test_decision_entries_streamed_with_task_id():
def test_manifest_contains_task_to_session_map():
def test_analyze_traces_joins_decisions_on_task_id():
def test_interpretability_dump_resolves_by_humaneval_id():   # the id-mismatch regression
```

### Commit
```
git add -A && git commit -m "phase-23: decision-log JSONL export + task_id<->session linking for qualitative analysis"
```

---

## PHASE 24 — Qualitative Metrics: Coherence / Interpretability / Stability [RQ1/RQ2]

**Goal:** Implement the thesis's qualitative criteria (انسجام تصمیم‌گیری، قابلیت تفسیر، پایداری بلندمدت) as
**deterministic** computations over the Phase-23 decision JSONL, so the qualitative chapter rests on numbers,
not prose.

### Tasks

- `eval/metrics/qualitative.py` (new):

```python
class QualitativeReport(BaseModel):
    contradiction_rate: float        # contradiction self_check issues / total decisions  (coherence, RQ2)
    rationale_coverage: float        # decisions with non-empty rationale / total          (interpretability)
    loop_rate: float                 # loop-flagged decisions / total                      (stability)
    oscillation_index: float         # repeated kind+payload-hash flips over a session     (stability, RQ3)
    by_interaction_length: dict      # metric trajectories vs interaction count            (ties to Phase 16)

def compute_qualitative(decisions_jsonl: str) -> QualitativeReport: ...
```

- `scripts/analyze_traces.py` — add `--qualitative` to emit a per-config `QualitativeReport`; compare A vs D to
  show whether memory/control reduce contradiction and oscillation as interaction length grows.

### Acceptance tests — `tests/unit/test_qualitative_metrics.py`

```python
def test_contradiction_rate_counts_contradiction_issues():
def test_rationale_coverage_full_when_all_have_rationale():
def test_loop_rate_uses_quality_gate_loop_flag():
def test_oscillation_index_detects_flip_flop_decisions():
def test_metrics_bucketed_by_interaction_length():
```

### Commit
```
git add -A && git commit -m "phase-24: deterministic qualitative metrics (coherence, interpretability, stability)"
```

---

## PHASE 25 — LangGraph Production Path OR Documented Deprecation [REQUIRES_USER_INPUT]

**Goal:** Resolve the honesty gap: the thesis presents a LangGraph FSM, but production uses the imperative
loop and `build_graph` runs only in tests with `MemorySaver` (handoff §3, §6). Either make LangGraph the real
path with durable `SqliteSaver` checkpointing, or formally deprecate it and document the imperative loop as the
FSM of record.

> `[REQUIRES_USER_INPUT]` — advisor/committee decision: is LangGraph a load-bearing thesis claim? Pick **Option A**
> (adopt) or **Option B** (deprecate) before implementing.

### Tasks — Option A (adopt LangGraph in production)

- `src/framework/orchestration/graph.py` — switch checkpointer to `SqliteSaver.from_conn_string(config.sqlite_path)`;
  ensure node functions wrap the *same* Planner/Executor Decision-Cycle calls (no logic fork).
- `session.py` — add `run_full_session(..., engine="graph")` that drives the compiled graph; keep `engine="loop"`
  as default until parity is shown. Transitions remain pure-Python `next_state`.

### Tasks — Option B (deprecate)

- Move `graph.py` under `src/framework/orchestration/_experimental/`, add a module docstring stating it is not
  the production path, and add a `docs/fsm_of_record.md` describing the imperative loop as the FSM (states,
  transitions, loop/escalate guards) with a one-paragraph thesis-text justification.

### Acceptance tests

Option A — `tests/integration/test_workflow.py` (extend):
```python
def test_graph_uses_sqlite_saver():
def test_graph_engine_reaches_done_on_passing_task(mock_slm):
def test_graph_and_loop_produce_same_terminal_outcome(mock_slm):   # parity
```
Option B — `tests/unit/test_deprecation.py`:
```python
def test_graph_marked_experimental_not_imported_by_session():
def test_fsm_of_record_doc_exists():
```

### Commit
```
git add -A && git commit -m "phase-25: LangGraph production adoption (SqliteSaver) OR documented deprecation"
```

---

## PHASE 26 — Cost / Latency / Token Accounting per Session

**Goal:** Substantiate the thesis's efficiency argument (SLMs cheaper than LLMs) with measured per-session
tokens, latency, and estimated cost. The `SLMClient` already returns `tokens_used` and `elapsed_ms`; nothing
aggregates them.

### Tasks

- `src/framework/orchestration/session.py` — accumulate `tokens_used` and `elapsed_ms` across all SLM calls in a
  session; add `tokens_total`, `latency_ms_total`, `llm_calls` to `RunResult` (extend the Pydantic model in
  `eval/metrics/sr.py`).
- `eval/metrics/cost.py` (new) — `estimate_cost(run_path, price_table: dict) -> dict`, reading per-model prices
  from `configs/models.yaml` (`price_per_1k_in`/`price_per_1k_out`, defaulting to 0 when unknown). No network.
- `scripts/generate_report.py` — add a cost/latency/token column block to the report.

### Acceptance tests — `tests/unit/test_cost_accounting.py`

```python
def test_run_result_accumulates_tokens_and_latency():
def test_estimate_cost_uses_price_table():
def test_estimate_cost_zero_when_price_unknown():
def test_llm_call_count_recorded_per_session():
```

### Commit
```
git add -A && git commit -m "phase-26: per-session cost/latency/token accounting"
```

---

## PHASE 27 — Reproducibility Bundle + Results-Chapter Automation (Curated Only)

**Goal:** Generate the thesis results tables from **curated** runs only — explicitly excluding the
do-not-cite runs the handoff lists (§5) — so the report can never silently include a 70%/invalid run again.

### Tasks

- `configs/cite_allowlist.yaml` (new) — the canonical run ids to cite (seed list, manifest-verified). The
  report generator reads *only* these unless `--all` is passed.
- `scripts/generate_report.py` — add `--curated` (default for the thesis report): join each cited run to its
  Phase-14 manifest, fail loudly if a cited run is missing its manifest or failed the Phase-13 quality gate,
  and emit SR/CER as `mean ± 95% CI` across the cited seeds (multi-seed CIs).
- Bundle: `scripts/make_repro_bundle.py` (new) — copies cited JSONL + manifests + decision JSONL into
  `artifacts/repro_bundle/` with a `MANIFEST_INDEX.md`; no keys, no full workspaces.

### Acceptance tests — `tests/unit/test_report_curated.py`

```python
def test_curated_report_excludes_non_allowlisted_runs():
def test_report_fails_on_cited_run_missing_manifest():
def test_report_rejects_cited_run_that_failed_quality_gate():
def test_ci_computed_across_seeds():
def test_repro_bundle_contains_no_secrets():
```

CLI gate:
```
python scripts/generate_report.py --curated --dry-run
```

### Commit
```
git add -A && git commit -m "phase-27: curated results-chapter automation + reproducibility bundle"
```

---

## PHASE 28 — Hardening (Registry Error Path, Parser Newline, ThinkingBudget Tests)

**Goal:** Close the latent correctness gaps the handoff flags (§4 Phase 1 risk, §4 Phase 4 parser note, §7.7):
the `registry.py` import bug on a bad profile env, the one missing JSON-repair pattern, and the untested
`ThinkingBudget`.

### Tasks

- `src/framework/slm/registry.py` — remove the fragile `list_profile_names` import from `config`; on an invalid
  `{ROLE}_PROFILE`/bundle, return a typed, actionable error listing valid profile names — never `ImportError`.
- `src/framework/error_control/parser.py` — add the 8th repair pattern (JSON strings containing literal
  newlines) noted as missing; keep it as a pure transform with a focused unit test.
- `src/framework/error_control/thinking.py` — add the unit coverage that Phase 4 omitted (`feed` aborts at
  limit, `reuse_context` returns prior context).

### Acceptance tests

```python
# tests/unit/test_slm_registry.py (extend)
def test_invalid_profile_env_returns_typed_error_not_importerror():
def test_error_lists_valid_profile_names():

# tests/unit/test_error_control.py (extend)
def test_parser_repairs_literal_newline_in_string():

# tests/unit/test_thinking_budget.py (new)
def test_thinking_budget_aborts_at_limit():
def test_thinking_budget_reuse_context_returns_prior():
```

### Commit
```
git add -A && git commit -m "phase-28: hardening (registry error path, parser newline repair, ThinkingBudget tests)"
```

---

## PHASE 29 — Retrieval-Mechanism Ablation + Redis Backend [RQ1] [REQUIRES_USER_INPUT]

**Goal:** Strengthen **RQ1** by testing whether the memory *mechanism* matters: compare the current keyword
Generative-Agents retrieval against a semantic (Chroma) retriever behind a config flag, and complete the
`RedisBackend` (currently `NotImplementedError`) so the persistent-memory backend is more than SQLite.

> `[REQUIRES_USER_INPUT]` — optional; only pursue if the committee wants a memory-mechanism comparison. Chroma is
> already a bootstrap dependency; Redis needs a running server for its tests (otherwise they skip).

### Tasks

- `src/framework/memory/retrieval.py` — add `SemanticRetriever` (sentence-transformers + Chroma) behind
  `memory.yaml: retrieval.mode: keyword|semantic`; the `retrieve_top_k` contract (typed `RetrievalItem`, 150-token
  cap) is unchanged so it drops into the Working-Memory builder without API changes.
- `src/framework/memory/backend.py` — implement `RedisBackend.write/read/query/append` against the
  `memory.yaml` Redis config with the documented 24 h TTL; `create_backend_from_env()` selects it on
  `MEMORY_BACKEND=redis`.
- `eval/scenarios/ablation.py` — add a `retrieval_mode` axis so config B/D can be run keyword vs semantic and
  the SR/CER delta attributed to the retrieval mechanism (RQ1 evidence).

### Acceptance tests

```python
# tests/unit/test_retrieval_semantic.py
def test_semantic_retriever_returns_typed_items_capped_150_tokens():
def test_retrieval_mode_flag_switches_backend():
def test_keyword_mode_is_default_and_unchanged():

# tests/unit/test_redis_backend.py
def test_redis_backend_round_trip_when_server_available():   # pytest.skip if no server
def test_create_backend_from_env_selects_redis():
```

### Commit
```
git add -A && git commit -m "phase-29: retrieval-mechanism ablation (keyword vs semantic) + Redis backend (RQ1)"
```

> **Dependency order (Phases 13+):** 13 → 14 → 15 → 16 unblock everything else. 17 must land before 19 (so config D
> exercises reflection). 18 should land before 19/20 if the headline ablation is to run on a true SLM. 23
> must land before 24 (qualitative metrics read the decision JSONL) and before 22's contradiction column.
> Phases 25–29 are independent and can be scheduled against the thesis timeline.

---

## Phase Overview — Phases 30+

> **Context for the implementing agent:** Phases 0–29 are DONE. The framework, eval harness, ablation runner,
> manifests, quality gate, decision JSONL, qualitative metrics, cost accounting, curated allowlist, and the
> LangGraph production path (`engine="graph"` + SqliteSaver) all exist and are dry-run-tested. **What is
> missing is curated, live, multi-seed evidence and the thesis write-up artifacts.** Phases 13–29 *built*
> the machinery; phases 30+ *run* it to produce citable numbers, then turn those numbers into tables and
> figures. Two facts from the handoff drive the ordering: (1) the cited `humaneval_hard` n=10 slice is
> near-ceiling — A/B 90% SR, C/D 100% SR — so the A→D contribution can't be cleanly separated (§7.3); and
> (2) the production default is DeepSeek `deepseek-v4-flash`, whose "small" status is contestable for a
> thesis about SLMs (§1, §4). Phase 30 fixes (1); Phase 32 addresses (2).

```
PHASE 30 → Discriminative hard slice (break the n=10 ceiling effect)        [RQ2]
PHASE 31 → Live multi-seed A–D ablation, DeepSeek (mean ± 95% CI)           [RQ2] [REQUIRES_USER_INPUT]
PHASE 32 → True-SLM live matrix (Qwen-7B + Devstral via OpenRouter)         [RQ2] [REQUIRES_USER_INPUT]
PHASE 33 → Keyword vs semantic retrieval live comparison                    [RQ1] [REQUIRES_USER_INPUT]
PHASE 34 → Efficiency chapter: SLM-vs-LLM cost/latency/token table          [REQUIRES_USER_INPUT]
PHASE 35 → MBPP full ablation n=50                                          [REQUIRES_USER_INPUT]
PHASE 36 → RQ3 live evidence: interaction-length + agent-count CER sweeps    [RQ3] [REQUIRES_USER_INPUT]
PHASE 37 → SWE-bench Lite pilot (5–10 instances)                            [REQUIRES_USER_INPUT]
PHASE 38 → Qualitative metrics + failure taxonomy on cited runs             [RQ1/RQ2]
PHASE 39 → Thesis tables & figures automation (curated-only, LaTeX)
PHASE 40 → Documentation pass + zipped reproducibility package
PHASE 41 → E2E regression smoke + optional Redis pilot                      [REQUIRES_USER_INPUT optional]
```

Same contract as the rest of `ROADMAP.md`: **Goal → Tasks → Acceptance tests → Commit**. Architecture
constraints are non-negotiable and untouched here: agents pass state only through memory stores; agents
communicate only via typed Pydantic messages; the SLM never decides transitions (`next_state()` is pure
Python); every LLM call goes through the Decision Cycle; tools keep the write-guard and atomic checkpoints.

> **Evidence phases never fabricate numbers.** For every `[REQUIRES_USER_INPUT]` run phase, the CI-checkable
> gate is a `--dry-run` / structural test that passes immediately (proving wiring) **plus** an evidence-gate
> test that passes only once the live run is on disk, has passed `assess_run()`, and is entered in
> `configs/cite_allowlist.yaml`. The evidence-gate test **skips cleanly** when traces are absent (CI without
> budget) and is the true DONE criterion once the live run completes. Any "D beats A" assertion uses the
> existing **skip-not-fail** pattern so a null/ceiling result is recorded, never faked.

---

## PHASE 30 — Discriminative Hard Slice (Break the Ceiling Effect) [RQ2]

**Goal:** The cited `humaneval_hard` n=10 slice is near-ceiling (A/B 90%, C/D 100%), so the memory/control/
error-control contribution can't be statistically separated (handoff §7.3). Build a larger, deterministically
harder, *frozen* slice on which config A drops well below ceiling, making the A→D delta measurable. No live API.

### Tasks

- `eval/datasets/_difficulty.py` (new) — extract the `difficulty_of(...)` heuristic shared by the HumanEval and
  MBPP adapters into one module (currently duplicated since Phase 15/20); keep behaviour identical (regression).
- `configs/humaneval_hard_ids.txt` — expand the frozen curated id list to ≥30 ids, selected as the top
  difficulty quantile (by `prompt_loc`, `n_assertions`, nested-loop/DP keywords). Exclude ids that config A
  already solves at every seed in existing traces (those add ceiling, not signal).
- `configs/eval.yaml` — add a frozen alias `discriminative: {dataset: humaneval, ids_file: humaneval_hard_ids.txt, n: 30, seed: 42}`. Leave `humaneval_hard` unchanged for backward compatibility.
- `eval/run_eval.py` / `eval/scenarios/ablation.py` — accept `--dataset discriminative`.

### Acceptance tests — extend `tests/unit/test_difficulty_slices.py`

```python
def test_difficulty_module_shared_by_humaneval_and_mbpp():   # both import eval.datasets._difficulty
def test_hard_slice_size_at_least_30():
def test_slice_is_frozen_and_deterministic():                # same ids for fixed seed across two loads
def test_discriminative_alias_resolves_in_eval_yaml():
def test_existing_humaneval_hard_alias_unchanged():          # regression
```

CLI gate (no budget):
```
python -m eval.run_eval --config A --dataset discriminative --n 5 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-30: discriminative frozen hard slice to break ceiling effect (RQ2)"
```

---

## PHASE 31 — Live Multi-Seed A–D Ablation, DeepSeek (mean ± 95% CI) [RQ2] [REQUIRES_USER_INPUT]

**Goal:** Produce the statistical core of the RQ2 result: A/B/C/D on the discriminative slice across seeds
41/42/43 with DeepSeek, reported as SR/CER mean ± 95% CI, with valid runs entered in the cite allowlist and
the curated report regenerated.

> `[REQUIRES_USER_INPUT]` — DeepSeek API budget. Cost ≈ 4 configs × 30 tasks × 3 seeds sessions. Confirm budget
> before running.

### Tasks

- Live run: `python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --profile-bundle deepseek`
  (quality-aborts on any invalid run — wired in Phase 19).
- `configs/cite_allowlist.yaml` — add section `humaneval_discriminative_deepseek` listing the 12 valid run ids
  (4 configs × 3 seeds), each with seed and quality-gate status.
- `tests/unit/test_cite_allowlist.py` (new) — validate every allowlist entry references an existing JSONL that
  passed `assess_run()` and carries required fields; **skip** entries whose trace file is absent (CI-safe).
- Regenerate: `python scripts/generate_report.py --curated` → curated section now shows per-config mean ± 95% CI.

### Acceptance tests

Structural gate (no budget):
```
python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --dry-run
pytest tests/unit/test_cite_allowlist.py        # passes/skips cleanly with no traces present
```

Evidence gate (after live run):
```python
def test_deepseek_discriminative_section_complete_and_valid():   # no skips for the 12 new ids
@pytest.mark.e2e
def test_ablation_d_geq_a_discriminative():
    """If D.SR >= A.SR + 5pp AND D.CER < A.CER → pass; else pytest.skip recording observed means
       (document ceiling, never assert a fabricated win)."""
```

### Commit
```
git add -A && git commit -m "phase-31: live multi-seed A-D ablation (DeepSeek) + allowlist + 95% CI (RQ2)"
```

---

## PHASE 32 — True-SLM Live Matrix (Qwen-7B + Devstral) [RQ2] [REQUIRES_USER_INPUT]

**Goal:** Protect the headline claim — "acceptable performance **without relying on LLMs**." The production
default is DeepSeek `v4-flash`, whose <30B "small" status is contestable (handoff §1, §4 Phase 1). Run the
A–D matrix on the `slm_small` bundle (Qwen-7B planner + Devstral executor via OpenRouter) so the thesis result
rests on a genuine SLM. A weaker model is expected to show *larger* A→D separation — strong RQ2 evidence.

> `[REQUIRES_USER_INPUT]` — `OPENROUTER_API_KEY` with budget, and committee confirmation that Qwen-7B/Devstral
> qualify as "small". The agent must not create accounts or write keys to the repo; the user fills `.env`.

### Tasks

- Verify bundle: `python scripts/smoke_test.py --bundle slm_small` must print `OUTCOME: solved`.
- Live run: `python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --profile-bundle slm_small`.
- `configs/cite_allowlist.yaml` — add section `humaneval_discriminative_slm_small`; quality-validate all runs.
- Regenerate curated report (now two provider blocks: DeepSeek vs slm_small).
- Record (analysis note in `thesis_evaluation_report.md`, not asserted) whether the D→A gap is larger on
  slm_small than on DeepSeek — the expected mechanism-helps-weaker-model finding.

### Acceptance tests

Structural gate:
```
pytest tests/unit/test_slm_profiles.py
python -m eval.scenarios.ablation --dataset discriminative --profile-bundle slm_small --dry-run
```

Evidence gate (after live run): `test_slm_small_discriminative_section_complete_and_valid()` in
`tests/unit/test_cite_allowlist.py` passes with no skips.

### Commit
```
git add -A && git commit -m "phase-32: true-SLM (Qwen-7B+Devstral) live A-D matrix (RQ2)"
```

---

## PHASE 33 — Keyword vs Semantic Retrieval Live Comparison [RQ1] [REQUIRES_USER_INPUT]

**Goal:** Direct RQ1 evidence — does the *memory mechanism* matter? Compare keyword (Generative Agents) vs
semantic (Chroma) retrieval on the memory-bearing configs (B and D), attributing any SR/CER and coherence delta
to the retrieval mechanism. Both modes exist (Phase 29) but no curated comparison run does (§7.5).

> `[REQUIRES_USER_INPUT]` — API budget. Reuse whichever provider bundle the committee designates as canonical.

### Tasks

- `eval/scenarios/retrieval_compare.py` (new) — thin wrapper over the ablation runner restricted to configs
  **B and D** (the only configs with memory on), iterating `--retrieval-mode keyword|semantic` over seeds.
- Live run on the discriminative slice, seeds 41/42/43, both modes.
- `configs/cite_allowlist.yaml` — sections `retrieval_keyword` and `retrieval_semantic`.
- Cross-link to Phase 24 metrics: compute contradiction & oscillation per mode (does semantic retrieval reduce
  incoherence as interaction length grows?).

### Acceptance tests — `tests/unit/test_retrieval_compare.py`

```python
def test_retrieval_compare_runs_only_b_and_d():
def test_retrieval_mode_flag_propagates_to_sessions():
def test_compare_table_has_mode_and_config_columns():
```

CLI gate (no budget):
```
python -m eval.scenarios.retrieval_compare --dataset discriminative --dry-run
```

Evidence gate: `test_retrieval_sections_complete_and_valid()` in `tests/unit/test_cite_allowlist.py`.

### Commit
```
git add -A && git commit -m "phase-33: keyword vs semantic retrieval live comparison (RQ1)"
```

---

## PHASE 34 — Efficiency Chapter: SLM-vs-LLM Cost/Latency/Token Table [REQUIRES_USER_INPUT]

**Goal:** Substantiate the thesis's "low-cost / locally deployable" claim with measured per-task tokens,
latency, and estimated cost, comparing slm_small against DeepSeek on the same slice. Pre–Phase-26 traces show
zero usage (§7.2); the Phase-31/32 runs carry real usage via `TrackingSLMClient`, so this phase aggregates them.

> `[REQUIRES_USER_INPUT]` — depends on Phases 31 and 32 having produced cited runs with non-zero usage fields.

### Tasks

- `configs/models.yaml` — add `price_per_1k_in` / `price_per_1k_out` for `deepseek-v4-flash`, `qwen2.5-coder-7b`,
  and `devstral-small` (use 0 with an explicit `price_known: false` flag where a public price is unavailable).
- `eval/metrics/efficiency.py` (new) — aggregate `tokens_total`, `latency_ms_total`, `llm_calls`, and
  `estimate_cost(...)` (Phase 26) per provider × config from cited JSONL; emit per-task means.
- `scripts/generate_report.py` — add `--efficiency` producing a provider × config table: SR, CER, tokens/task,
  latency/task, $/task, with unknown prices clearly flagged (never silently 0).

### Acceptance tests — `tests/unit/test_efficiency.py`

```python
def test_efficiency_aggregates_usage_per_provider_config():
def test_estimated_usd_uses_price_table():
def test_unknown_price_is_flagged_not_silently_zero():
def test_efficiency_table_compares_deepseek_vs_slm_small():
```

CLI gate:
```
python scripts/generate_report.py --efficiency --dry-run
```

### Commit
```
git add -A && git commit -m "phase-34: efficiency chapter (SLM-vs-LLM cost/latency/token table)"
```

---

## PHASE 35 — MBPP Full Ablation n=50 [REQUIRES_USER_INPUT]

**Goal:** A second benchmark for external validity — A–D on MBPP n=50 (handoff §7: adapter ready, no live runs),
so the thesis isn't a single-dataset result.

> `[REQUIRES_USER_INPUT]` — API budget.

### Tasks

- Confirm the MBPP adapter maps to the session task shape and `difficulty_of` works on `MBPPTask`
  (Phase 20/30 shared module).
- Live run: `python -m eval.scenarios.ablation --dataset mbpp --n 50 --seeds 41,42,43` (or seed 42 if budget-limited).
- Quality-validate; `configs/cite_allowlist.yaml` section `mbpp_50`; regenerate curated report.

### Acceptance tests

CLI gate (no budget):
```
python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run
```

Evidence gate: `test_mbpp50_section_complete_and_valid()` in `tests/unit/test_cite_allowlist.py`; honest
`@pytest.mark.e2e test_ablation_d_geq_a_mbpp()` (skip-not-fail).

### Commit
```
git add -A && git commit -m "phase-35: MBPP n=50 A-D ablation + curated traces"
```

---

## PHASE 36 — RQ3 Live Evidence: Interaction-Length + Agent-Count CER Sweeps [RQ3] [REQUIRES_USER_INPUT]

**Goal:** The central RQ3 numbers: cumulative error (CER) as a function of interaction length (L=2,4,6,8) and of
agent count (1 vs 2 agents). Both harnesses exist (Phases 16, 22) but lack live curated traces, and the
Phase-22 contradiction column is still stubbed pending decision JSONL (now available from Phase 23).

> `[REQUIRES_USER_INPUT]` — API budget.

### Tasks

- Live interaction-length sweep: `python -m eval.scenarios.interaction_length --config A --config D --levels 2,4,6,8 --seeds 41,42,43` (A and D so the framework delta is visible as L grows).
- Live agent-count: `python -m eval.scenarios.agent_count --dataset multistep --seeds 41,42,43`.
- `eval/scenarios/agent_count.py` — replace the contradiction-count stub with the real value computed from the
  Phase-23 decision JSONL (`eval/decision_log.py`).
- Quality-validate; `configs/cite_allowlist.yaml` sections `rq3_interaction_length`, `rq3_agent_count`.
- Produce CER-vs-L and CER-vs-agents tables (expectation, not asserted: A's CER rises faster with L than D's).

### Acceptance tests

```python
# tests/unit/test_ablation_runner.py (extend)
def test_agent_count_contradiction_from_decision_log():    # no longer a stub
# tests/unit/test_interaction_length.py (extend)
def test_sweep_emits_cer_per_level_per_config():
```

CLI gates (no budget):
```
python -m eval.scenarios.interaction_length --config D --levels 2,4,6,8 --dry-run
python -m eval.scenarios.agent_count --dataset multistep --dry-run
```

Evidence gate: `test_rq3_sections_complete_and_valid()` in `tests/unit/test_cite_allowlist.py`.

### Commit
```
git add -A && git commit -m "phase-36: RQ3 live evidence (interaction-length + agent-count CER sweeps)"
```

---

## PHASE 37 — SWE-bench Lite Pilot (5–10 instances) [REQUIRES_USER_INPUT]

**Goal:** Validate the Docker grading path (Phase 21) on a small set of real SWE-bench Lite instances and report
whether the framework completes genuine repository-repair sessions. Pilot scale — reported as illustrative, not
a full benchmark claim.

> `[REQUIRES_USER_INPUT]` — Docker available on the host **and** API budget. The agent must not install Docker or
> pull untrusted images without the user enabling it.

### Tasks

- Run config D on 5–10 SWE-bench Lite instances via the Phase-21 Docker harness; capture `FAIL_TO_PASS` outcomes.
- Quality-validate (no zero-interaction); `configs/cite_allowlist.yaml` section `swebench_pilot` clearly marked
  pilot/illustrative (small n).
- Record per-instance outcome + a short failure note for any unresolved instance (feeds Phase 38 taxonomy).

### Acceptance tests — `tests/unit/test_swebench_docker.py` (extend)

```python
def test_pilot_run_records_per_instance_outcome():
def test_swe_pilot_skips_cleanly_when_docker_absent(monkeypatch):
```

CLI gate (structural; Docker run is the evidence step):
```
python -m eval.run_eval --config D --dataset swebench --n 1 --dry-run
```

### Commit
```
git add -A && git commit -m "phase-37: SWE-bench Lite pilot (Docker grading path validation)"
```

---

## PHASE 38 — Qualitative Metrics + Failure Taxonomy on Cited Runs [RQ1/RQ2]

**Goal:** Turn the cited decision-log JSONL (from Phases 31–33, 36) into the thesis's qualitative chapter:
contradiction rate, oscillation index, and rationale coverage per config (Phase 24), plus a failure taxonomy
(escalate vs max_steps vs unresolvable) across configs. Deterministic, no budget.

### Tasks

- `eval/metrics/failure_taxonomy.py` (new) — classify each `RunResult.outcome` plus its escalation reason from
  the decision JSONL into a typed taxonomy; produce counts per config and per provider.
- `scripts/analyze_traces.py` — add `--taxonomy`; ensure `--qualitative` and `--compare-a-d` run over the cited
  run glob and emit the A-vs-D and keyword-vs-semantic comparison tables for the chapter.
- Output a single qualitative summary table (coherence/interpretability/stability + taxonomy) per provider.

### Acceptance tests — `tests/unit/test_failure_taxonomy.py` (+ extend `test_qualitative_metrics.py`)

```python
def test_taxonomy_classifies_each_outcome_kind():
def test_taxonomy_counts_per_config_and_provider():
def test_taxonomy_reads_decision_jsonl_not_checkpoints():
def test_qualitative_runs_over_cited_glob():
```

CLI gate:
```
python scripts/analyze_traces.py --qualitative --compare-a-d --taxonomy --dry-run
```

### Commit
```
git add -A && git commit -m "phase-38: qualitative metrics + failure taxonomy on cited runs (RQ1/RQ2)"
```

---

## PHASE 39 — Thesis Tables & Figures Automation (Curated-Only, LaTeX)

**Goal:** Auto-generate the results-chapter tables and figures from **curated runs only** — never the dirty
aggregate — in LaTeX + PNG, so the write-up is reproducible and cannot accidentally include a do-not-cite run
(e.g. `D_humaneval_20260520T085222Z`).

### Tasks

- `scripts/make_figures.py` (new, matplotlib) — SR and CER bar charts per config, CER-vs-L line plot, and the
  DeepSeek-vs-slm_small comparison; reads the curated report only; writes `artifacts/figures/*.png`.
- `scripts/generate_report.py` — add `--latex` emitting LaTeX tables (SR/CER mean ± 95% CI, efficiency,
  qualitative) to `artifacts/tables/*.tex`.
- Guard: both tools **refuse** to emit if any referenced run is missing from `cite_allowlist.yaml` or failed
  `assess_run()`.

### Acceptance tests — `tests/unit/test_report_latex.py`, `tests/unit/test_figures.py`

```python
def test_latex_tables_emitted_with_ci():
def test_latex_refuses_noncurated_run():
def test_figures_generated_from_curated_only():
def test_figure_refuses_run_that_failed_quality_gate():
```

CLI gate:
```
python scripts/generate_report.py --latex --dry-run && python scripts/make_figures.py --dry-run
```

### Commit
```
git add -A && git commit -m "phase-39: thesis tables + figures automation (curated-only, LaTeX export)"
```

---

## PHASE 40 — Documentation Pass + Zipped Reproducibility Package

**Goal:** Align the docs with the graph-default reality (the early ROADMAP text still implies a loop default /
OpenRouter-only client) and ship a committee-ready, secret-free reproducibility package.

### Tasks

- `docs/architecture.md` (new) — a diagram + prose reflecting the actual production path
  (`run_full_session(engine="graph")` + SqliteSaver), the three pillars, and the A–D ablation matrix; remove
  stale loop-default / OpenRouter-only claims.
- `docs/reproducibility.md` (new) — exact commands to reproduce each cited table and figure from manifests.
- `scripts/make_repro_bundle.py` — add `--zip`: bundle cited JSONL + manifests + decision JSONL + `artifacts/tables`
  + `artifacts/figures` + `MANIFEST_INDEX.md` into `artifacts/repro_bundle.zip`; **no** keys, **no** full workspaces.

### Acceptance tests — `tests/unit/test_repro_package.py`

```python
def test_bundle_zip_created():
def test_bundle_contains_no_secrets():            # scans for key/token-shaped strings
def test_bundle_includes_manifest_index():
def test_bundle_only_references_cited_runs():
def test_architecture_doc_states_graph_default():
```

CLI gate:
```
python scripts/make_repro_bundle.py --zip --dry-run
```

### Commit
```
git add -A && git commit -m "phase-40: documentation pass + zipped reproducibility package"
```

---

## PHASE 41 — E2E Regression Smoke + Optional Redis Pilot [REQUIRES_USER_INPUT optional]

**Goal:** Guard against regressions during the write-up sprint, and (optionally) validate the Redis backend
against a real server (the Phase-29 live round-trip is currently skipped, §7.4).

> `[REQUIRES_USER_INPUT]` (optional) — the smoke run needs a provider key; the Redis pilot needs a local Redis
> server. Both degrade to **skip** when unavailable so CI stays green.

### Tasks

- `tests/e2e/test_regression_smoke.py` (new) — config D on `humaneval_hard` n=3, marked `@pytest.mark.e2e`;
  asserts the session reaches `solved`/`escalate` without crashing and the run passes `assess_run()`.
- `.github/workflows/smoke.yml` (optional) — on dispatch/nightly, run the smoke when a provider key secret is
  present; skip if absent.
- Redis pilot — with `MEMORY_BACKEND=redis` and a local server, run the existing skipped
  `test_redis_backend` live round-trip; note behaviour under repeated sessions in `docs/reproducibility.md`.

### Acceptance tests

```
pytest tests/e2e/test_regression_smoke.py --collect-only      # structural, no key needed
pytest tests/unit/test_redis_backend.py                       # skips without server, passes with
```

Evidence step (needs key): `pytest tests/e2e/test_regression_smoke.py -m e2e`.

### Commit
```
git add -A && git commit -m "phase-41: e2e regression smoke + optional Redis live pilot"
```

---

## Test Gates — Phases 30+

```bash
# Before marking any phase DONE, run its gate:
PHASE 30: pytest tests/unit/test_difficulty_slices.py && python -m eval.run_eval --config A --dataset discriminative --n 5 --dry-run
PHASE 31: python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --dry-run && pytest tests/unit/test_cite_allowlist.py
PHASE 32: pytest tests/unit/test_slm_profiles.py && python -m eval.scenarios.ablation --dataset discriminative --profile-bundle slm_small --dry-run
PHASE 33: pytest tests/unit/test_retrieval_compare.py && python -m eval.scenarios.retrieval_compare --dataset discriminative --dry-run
PHASE 34: pytest tests/unit/test_efficiency.py && python scripts/generate_report.py --efficiency --dry-run
PHASE 35: python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run
PHASE 36: pytest tests/unit/test_ablation_runner.py tests/unit/test_interaction_length.py && python -m eval.scenarios.agent_count --dataset multistep --dry-run
PHASE 37: pytest tests/unit/test_swebench_docker.py            # + Docker instance run (needs Docker + key)
PHASE 38: pytest tests/unit/test_failure_taxonomy.py tests/unit/test_qualitative_metrics.py
PHASE 39: pytest tests/unit/test_report_latex.py tests/unit/test_figures.py && python scripts/generate_report.py --latex --dry-run
PHASE 40: pytest tests/unit/test_repro_package.py && python scripts/make_repro_bundle.py --zip --dry-run
PHASE 41: pytest tests/e2e/test_regression_smoke.py --collect-only && pytest tests/unit/test_redis_backend.py
```

> **Dependency order:** 30 unblocks all live ablation (31, 32, 33, 35, 36 run on the discriminative slice).
> 34 depends on 31+32 (needs cited runs with non-zero usage). 38/39 depend on the cited decision JSONL and
> curated runs that 31–33 and 36 produce. 40 and 41 are independent and can run anytime. If budget is tight,
> the minimum publishable core is **30 → 31 → 32 → 38 → 39** (discriminative slice, both providers, qualitative
> analysis, automated tables) — 33/35/36/37 add breadth, 34/40/41 add polish.

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
PHASE 13: pytest tests/unit/test_run_quality.py tests/unit/test_api_probe_retry.py
PHASE 14: pytest tests/unit/test_manifest.py && python -m eval.run_eval --config D --dataset humaneval --task-id HumanEval/0 --dry-run
PHASE 15: pytest tests/unit/test_difficulty_slices.py
PHASE 16: pytest tests/unit/test_interaction_length.py && python -m eval.scenarios.interaction_length --config D --levels 2,4,6,8 --dry-run
PHASE 17: pytest tests/integration/test_reflection_revise.py
PHASE 18: pytest tests/unit/test_slm_profiles.py            # + e2e with slm_small bundle (needs key)
PHASE 19: python -m eval.scenarios.ablation --dataset humaneval_hard --seeds 41,42,43 --dry-run && pytest tests/unit/test_ablation_runner.py
PHASE 20: python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run
PHASE 21: pytest tests/unit/test_swebench_docker.py         # + Docker run (needs Docker + key)
PHASE 22: python -m eval.scenarios.agent_count --dataset multistep --dry-run && pytest tests/unit/test_ablation_runner.py
PHASE 23: pytest tests/unit/test_decision_jsonl.py tests/unit/test_analyze_traces.py
PHASE 24: pytest tests/unit/test_qualitative_metrics.py
PHASE 25: pytest tests/integration/test_workflow.py          # Option A; or tests/unit/test_deprecation.py for Option B
PHASE 26: pytest tests/unit/test_cost_accounting.py
PHASE 27: pytest tests/unit/test_report_curated.py && python scripts/generate_report.py --curated --dry-run
PHASE 28: pytest tests/unit/test_slm_registry.py tests/unit/test_error_control.py tests/unit/test_thinking_budget.py
PHASE 29: pytest tests/unit/test_retrieval_semantic.py tests/unit/test_redis_backend.py
PHASE 30: pytest tests/unit/test_difficulty_slices.py && python -m eval.run_eval --config A --dataset discriminative --n 5 --dry-run
PHASE 31: python -m eval.scenarios.ablation --dataset discriminative --seeds 41,42,43 --dry-run && pytest tests/unit/test_cite_allowlist.py
PHASE 32: pytest tests/unit/test_slm_profiles.py && python -m eval.scenarios.ablation --dataset discriminative --profile-bundle slm_small --dry-run
PHASE 33: pytest tests/unit/test_retrieval_compare.py && python -m eval.scenarios.retrieval_compare --dataset discriminative --dry-run
PHASE 34: pytest tests/unit/test_efficiency.py && python scripts/generate_report.py --efficiency --dry-run
PHASE 35: python -m eval.run_eval --config D --dataset mbpp --n 5 --dry-run
PHASE 36: pytest tests/unit/test_ablation_runner.py tests/unit/test_interaction_length.py && python -m eval.scenarios.agent_count --dataset multistep --dry-run
PHASE 37: pytest tests/unit/test_swebench_docker.py
PHASE 38: pytest tests/unit/test_failure_taxonomy.py tests/unit/test_qualitative_metrics.py
PHASE 39: pytest tests/unit/test_report_latex.py tests/unit/test_figures.py && python scripts/generate_report.py --latex --dry-run
PHASE 40: pytest tests/unit/test_repro_package.py && python scripts/make_repro_bundle.py --zip --dry-run
PHASE 41: pytest tests/e2e/test_regression_smoke.py --collect-only && pytest tests/unit/test_redis_backend.py
```
