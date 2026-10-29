"""An optional early reminder to write a plausible artifact before refining it."""

from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.trace import record, sync
from agent.prompts import EARLY_DELIVERABLE_MESSAGE
from agent.state import AgentState


def needs_deliverable(state: AgentState, ctx: GraphContext) -> bool:
    return (
        ctx.early_deliverable
        and ctx.deliverable_turn > 0
        and state.turns >= ctx.deliverable_turn
        and state.action_kind == "shell"
        and state.run_command
        and not any(row.get("node") == "deliverable" for row in state.node_trace)
    )


async def deliverable(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    ctx = runtime.context
    state.messages.append({"role": "user", "content": EARLY_DELIVERABLE_MESSAGE})
    record(state, ctx, "deliverable")
    state.node_trace[-1]["scheduled_turn"] = ctx.deliverable_turn
    sync(state, ctx.harbor)
    return {"messages": state.messages, "node_trace": state.node_trace}
