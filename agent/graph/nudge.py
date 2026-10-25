"""A reply that named no command: nudge once, or give up after a streak."""

from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.trace import record, sync
from agent.prompts import ACT_NUDGE_MESSAGE, NUDGE_MESSAGE
from agent.state import AgentState


async def nudge(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    ctx = runtime.context
    state.turns_without_action += 1
    if not state.last_truncated:
        state.no_command_replies += 1
    if state.turns_without_action >= ctx.max_turns_without_action:
        state.stop_reason = "no_action"
        ctx.logger.info(
            "stopping after %d turns with no command", state.turns_without_action
        )
    elif state.last_truncated:
        state.messages.append({"role": "user", "content": NUDGE_MESSAGE})
    else:
        # Ask for the command, and sample the next reply hotter so it
        # cannot repeat this one. One turn only; call_model clears it.
        state.next_temperature = ctx.no_command_temperature
        state.messages.append({"role": "user", "content": ACT_NUDGE_MESSAGE})
    record(state, ctx, "nudge")
    sync(state, ctx.harbor)
    return {
        "messages": state.messages,
        "turns_without_action": state.turns_without_action,
        "no_command_replies": state.no_command_replies,
        "stop_reason": state.stop_reason,
        "next_temperature": state.next_temperature,
        "node_trace": state.node_trace,
    }
