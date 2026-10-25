"""Run the command in the task container and hand the output back."""

from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.trace import record, sync
from agent.prompts import observation_message
from agent.state import AgentState
from agent.tools import parse_exit_code, run_shell


async def execute(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    ctx = runtime.context
    ctx.logger.info("turn %d: %s", state.turns, state.command[:200])
    observation = await run_shell(
        ctx.environment, state.command, timeout_sec=ctx.command_timeout_sec
    )
    after = state.guard.after(state.command, parse_exit_code(observation))
    note = state.before_note or after.note
    content = observation_message(observation)
    if note:
        content = f"{content}\n\n{note}"
    state.messages.append({"role": "user", "content": content})
    if after.stop:
        state.stopped_by_guard = "consecutive_failures"
        ctx.logger.info("stopping: %s", after.note)
    record(state, ctx, "execute")
    sync(state, ctx.harbor)
    return {
        "messages": state.messages,
        "guard": state.guard,
        "stopped_by_guard": state.stopped_by_guard,
        "node_trace": state.node_trace,
    }
