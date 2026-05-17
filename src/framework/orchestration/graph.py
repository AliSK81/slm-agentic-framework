"""LangGraph workflow graph assembly."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from framework.control.ledger import build_progress_ledger
from framework.control.workflow import (
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

logger = logging.getLogger(__name__)

NodeFn = Callable[[WorkflowState], WorkflowState]


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


def build_graph(
    planner: Any,
    executor: Any,
    memory: MemoryStores,
    config: dict[str, Any] | None = None,
) -> Any:
    """Compile LangGraph workflow with checkpointing."""
    _ = config
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
        if target == "DONE":
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

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
