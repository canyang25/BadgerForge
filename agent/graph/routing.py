"""Edges between the loop nodes. Same stops as the old ``for`` loop."""

from typing import Literal

from langgraph.graph import END
from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.deliverable import needs_deliverable
from agent.graph.progress import needs_progress
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
) -> Literal["deliverable", "progress", "call_model", "__end__"]:
    if state.stop_reason == "no_action":
        return END
    return _continue(state, runtime)


def route_after_guard(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["execute", "deliverable", "progress", "call_model", "__end__"]:
    if state.run_command:
        return "execute"
    return _continue(state, runtime)


def route_after_execute(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["shape", "deliverable", "progress", "call_model", "__end__"]:
    if state.stopped_by_guard or state.turns >= runtime.context.max_turns:
        return END
    if runtime.context.observation_shape and state.observation_kind:
        return "shape"
    return _continue(state, runtime)


def route_after_shape(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["deliverable", "progress", "call_model", "__end__"]:
    return _continue(state, runtime)


def route_after_deliverable(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["progress", "call_model", "__end__"]:
    if state.turns >= runtime.context.max_turns:
        return END
    return "progress" if needs_progress(state, runtime.context) else "call_model"


def route_after_progress(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["call_model", "__end__"]:
    if state.turns >= runtime.context.max_turns:
        return END
    return "call_model"


def _continue(
    state: AgentState, runtime: Runtime[GraphContext]
) -> Literal["deliverable", "progress", "call_model", "__end__"]:
    if state.turns >= runtime.context.max_turns:
        return END
    if needs_deliverable(state, runtime.context):
        return "deliverable"
    if needs_progress(state, runtime.context):
        return "progress"
    return "call_model"
