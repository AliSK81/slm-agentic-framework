"""LangGraph workflow graph assembly."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from framework.control.ablation import AblationSettings
from framework.control.ledger import build_progress_ledger
from framework.control.workflow import (
    DONE,
    STATE_DISPATCH,
    STATE_ESCALATE,
    STATE_EVALUATE,
    STATE_EXECUTE,
    STATE_PLAN,
    STATE_REVISE,
    WorkflowState,
    next_state,
)
from framework.memory.stores import MemoryStores
from framework.orchestration.executor import ExecutorAgent
from framework.orchestration.planner import PlannerAgent
from framework.orchestration.verify import Verifier

logger = logging.getLogger(__name__)

NodeFn = Callable[[WorkflowState], WorkflowState]


def _sqlite_conn_string(db_path: Path) -> str:
    """Return a filesystem path for :meth:`SqliteSaver.from_conn_string`.

    LangGraph passes this value directly to ``sqlite3.connect`` (not a SQLAlchemy
    URI), so we use an absolute path with parent directories created first.
    """
    resolved = db_path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved.as_posix()


@contextmanager
def sqlite_checkpointer(db_path: Path) -> Iterator[Any]:
    """Open a durable :class:`SqliteSaver` for LangGraph checkpointing."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    with SqliteSaver.from_conn_string(_sqlite_conn_string(db_path)) as saver:
        yield saver


def _default_planner_plan(state: WorkflowState) -> WorkflowState:
    return {
        **state,
        "current_state": STATE_PLAN,
        "step_count": int(state.get("step_count", 0)) + 1,
    }


def _default_planner_dispatch(state: WorkflowState) -> WorkflowState:
    return {**state, "current_state": STATE_DISPATCH}


def _default_executor_execute(state: WorkflowState) -> WorkflowState:
    return {**state, "current_state": STATE_EXECUTE}


def _make_evaluate_node(memory: MemoryStores) -> NodeFn:
    def evaluation_node(state: WorkflowState) -> WorkflowState:
        build_progress_ledger(state, memory)
        return {**state, "current_state": STATE_EVALUATE}

    return evaluation_node


def _make_revise_node(memory: MemoryStores, revise_fn: Callable[..., str] | None) -> NodeFn:
    def revise_node(state: WorkflowState) -> WorkflowState:
        if revise_fn is not None:
            revise_fn(state, memory)
        return {
            **state,
            "current_state": STATE_REVISE,
            "retry_count": int(state.get("retry_count", 0)) + 1,
        }

    return revise_node


def _escalation_node(state: WorkflowState) -> WorkflowState:
    return {**state, "current_state": STATE_ESCALATE}


@dataclass
class SessionGraphDeps:
    """Bindings for a production session graph (same agents as imperative loop)."""

    planner: PlannerAgent
    executor: ExecutorAgent
    memory: MemoryStores
    workspace: Path
    verifier: Verifier
    goal: str
    settings: AblationSettings
    planner_enabled: bool = True


def _compile_session_graph(deps: SessionGraphDeps, checkpointer: Any) -> Any:
    """Compile LangGraph with session-faithful nodes (evaluate + revise + reflection)."""
    from framework.orchestration.session import _ensure_work_subtasks, _run_revise_reflection

    def plan_node(state: WorkflowState) -> WorkflowState:
        if not state.get("planned"):
            if deps.planner_enabled:
                deps.planner.plan_node(state)
            _ensure_work_subtasks(deps.memory, state["session_id"], deps.goal)
            state = {**state, "planned": True}
            state["step_count"] = int(state.get("step_count", 0)) + 1
        return {**state, "current_state": STATE_PLAN}

    def dispatch_node(state: WorkflowState) -> WorkflowState:
        return deps.planner.dispatch_node(state)

    def execute_node(state: WorkflowState) -> WorkflowState:
        return deps.executor.execute_node(state)

    def evaluate_node(state: WorkflowState) -> WorkflowState:
        evaluation = deps.verifier.evaluate(deps.workspace).as_dict()
        updated: WorkflowState = {
            **state,
            "last_evaluation": evaluation,
            "current_state": STATE_EVALUATE,
            "step_count": int(state.get("step_count", 0)) + 1,
        }
        if deps.settings.control:
            build_progress_ledger(updated, deps.memory)
        return updated

    def revise_node(state: WorkflowState) -> WorkflowState:
        updated = {
            **state,
            "current_state": STATE_REVISE,
            "retry_count": int(state.get("retry_count", 0)) + 1,
        }
        return _run_revise_reflection(
            updated,
            deps.memory,
            deps.goal,
            deps.planner._cycle._slm,
            deps.settings,
        )

    def router(state: WorkflowState) -> str:
        if int(state.get("step_count", 0)) >= int(state.get("max_steps", 15)):
            evaluation = state.get("last_evaluation") or {}
            return "DONE" if evaluation.get("passed") else STATE_ESCALATE
        if deps.settings.control:
            target = next_state(state, deps.memory)
        else:
            evaluation = state.get("last_evaluation") or {}
            if evaluation.get("passed"):
                target = DONE
            elif int(state.get("retry_count", 0)) >= int(state.get("max_retries", 3)):
                target = STATE_ESCALATE
            else:
                target = STATE_REVISE
        if target == DONE:
            return "DONE"
        return target

    builder = StateGraph(WorkflowState)
    builder.add_node(STATE_PLAN, plan_node)
    builder.add_node(STATE_DISPATCH, dispatch_node)
    builder.add_node(STATE_EXECUTE, execute_node)
    builder.add_node(STATE_EVALUATE, evaluate_node)
    builder.add_node(STATE_REVISE, revise_node)
    builder.add_node(STATE_ESCALATE, _escalation_node)

    builder.set_entry_point(STATE_PLAN)
    builder.add_edge(STATE_PLAN, STATE_DISPATCH)
    builder.add_edge(STATE_DISPATCH, STATE_EXECUTE)
    builder.add_edge(STATE_EXECUTE, STATE_EVALUATE)
    builder.add_conditional_edges(
        STATE_EVALUATE,
        router,
        {
            STATE_DISPATCH: STATE_DISPATCH,
            STATE_REVISE: STATE_REVISE,
            "DONE": END,
            STATE_ESCALATE: STATE_ESCALATE,
        },
    )
    builder.add_edge(STATE_REVISE, STATE_EXECUTE)
    builder.add_edge(STATE_ESCALATE, END)

    return builder.compile(checkpointer=checkpointer)


def build_graph(
    planner: Any,
    executor: Any,
    memory: MemoryStores,
    config: dict[str, Any] | None = None,
    *,
    sqlite_path: Path | None = None,
    session_deps: SessionGraphDeps | None = None,
) -> Any:
    """Compile LangGraph workflow with checkpointing.

    When ``session_deps`` is set, uses production session nodes. Otherwise uses
    lightweight defaults for structural tests.
    """
    _ = config
    if session_deps is not None:
        if sqlite_path is None:
            raise ValueError("sqlite_path is required when session_deps is provided")
        with sqlite_checkpointer(sqlite_path) as checkpointer:
            return _compile_session_graph(session_deps, checkpointer)

    plan_node = getattr(planner, "plan_node", _default_planner_plan)
    dispatch_node = getattr(planner, "dispatch_node", _default_planner_dispatch)
    execute_node = getattr(executor, "execute_node", _default_executor_execute)
    revise_fn = getattr(planner, "revise_node", None)

    builder = StateGraph(WorkflowState)
    builder.add_node(STATE_PLAN, plan_node)
    builder.add_node(STATE_DISPATCH, dispatch_node)
    builder.add_node(STATE_EXECUTE, execute_node)
    builder.add_node(STATE_EVALUATE, _make_evaluate_node(memory))
    builder.add_node(STATE_REVISE, _make_revise_node(memory, revise_fn))
    builder.add_node(STATE_ESCALATE, _escalation_node)

    builder.set_entry_point(STATE_PLAN)
    builder.add_edge(STATE_PLAN, STATE_DISPATCH)
    builder.add_edge(STATE_DISPATCH, STATE_EXECUTE)
    builder.add_edge(STATE_EXECUTE, STATE_EVALUATE)

    def router(state: WorkflowState) -> str:
        target = next_state(state, memory)
        if target == DONE:
            return "DONE"
        return target

    builder.add_conditional_edges(
        STATE_EVALUATE,
        router,
        {
            STATE_DISPATCH: STATE_DISPATCH,
            STATE_REVISE: STATE_REVISE,
            "DONE": END,
            STATE_ESCALATE: STATE_ESCALATE,
        },
    )
    builder.add_edge(STATE_REVISE, STATE_EXECUTE)
    builder.add_edge(STATE_ESCALATE, END)

    if sqlite_path is not None:
        with sqlite_checkpointer(sqlite_path) as checkpointer:
            return builder.compile(checkpointer=checkpointer)
    return builder.compile(checkpointer=MemorySaver())


def run_session_graph(
    deps: SessionGraphDeps,
    initial_state: WorkflowState,
    *,
    sqlite_path: Path,
    recursion_limit: int = 40,
) -> WorkflowState:
    """Invoke the compiled session graph with durable SQLite checkpointing."""
    run_config = {
        "configurable": {"thread_id": initial_state["session_id"]},
        "recursion_limit": recursion_limit,
    }
    with sqlite_checkpointer(sqlite_path) as checkpointer:
        graph = _compile_session_graph(deps, checkpointer)
        graph.update_state(run_config, initial_state)
        result = graph.invoke(None, run_config)
    if isinstance(result, dict):
        return result  # type: ignore[return-value]
    return result.values  # type: ignore[no-any-return, union-attr]


def checkpointer_kind(sqlite_path: Path) -> Literal["sqlite", "memory"]:
    """Return which checkpointer type ``build_graph`` would use."""
    return "sqlite" if sqlite_path is not None else "memory"
