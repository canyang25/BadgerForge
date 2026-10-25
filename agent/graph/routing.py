"""Edges between the loop nodes. Same stops as the old ``for`` loop."""

from typing import Literal

from langgraph.graph import END
from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.state import AgentState


def route_entry(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["call_model", "__end__"]:
    if state.turns >= runtime.context.max_turns:
        return END
    return "call_model"


def route_after_model(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["nudge", "guard", "__end__"]:
    if state.finished:
        return END
    if state.action_kind == "none":
        return "nudge"
    return "guard"


def route_after_nudge(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["call_model", "__end__"]:
    if state.stop_reason == "no_action" or state.turns >= runtime.context.max_turns:
        return END
    return "call_model"


def route_after_guard(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["execute", "call_model", "__end__"]:
    if state.run_command:
        return "execute"
    if state.turns >= runtime.context.max_turns:
        return END
    return "call_model"


def route_after_execute(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["call_model", "__end__"]:
    if state.stopped_by_guard or state.turns >= runtime.context.max_turns:
        return END
    return "call_model"
