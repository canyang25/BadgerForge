"""Ask the loop guard whether this command is worth running."""

from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.trace import record, sync
from agent.state import AgentState


async def guard(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    ctx = runtime.context
    verdict = state.guard.before(state.command)
    state.run_command = verdict.run
    state.before_note = verdict.note
    if not verdict.run:
        ctx.logger.info(
            "turn %d: refused repeat: %s", state.turns, state.command[:120]
        )
        state.messages.append({"role": "user", "content": verdict.note})
    record(state, ctx, "guard")
    sync(state, ctx.harbor)
    return {
        "messages": state.messages,
        "guard": state.guard,
        "run_command": state.run_command,
        "before_note": state.before_note,
        "node_trace": state.node_trace,
    }
