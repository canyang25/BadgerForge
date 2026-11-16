"""Run the command in the task container and hand the output back."""

from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.shape import classify_observation
from agent.graph.trace import measure_step, record, sync
from agent.prompts import observation_message
from agent.state import AgentState
from agent.tools import parse_exit_code, run_shell


async def execute(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    ctx = runtime.context
    ctx.logger.info("turn %d: %s", state.turns, state.command[:200])
    with measure_step(ctx, "execute", state.turns) as timing:
        observation = await run_shell(
            ctx.environment, state.command, timeout_sec=ctx.command_timeout_sec
        )
    return_code = parse_exit_code(observation)
    after = state.guard.after(
        state.command, return_code, observation=observation if ctx.loop_recovery else ""
    )
    note = state.before_note or after.note
    denied_site = state.guard.new_denial_streak() if ctx.loop_recovery else None
    if denied_site:
        pivot = (
            f"Three consecutive commands reported HTTP 403 from {denied_site}. "
            "Use a different source or a local approach in your next command."
        )
        note = f"{note}\n\n{pivot}" if note else pivot
    content = observation_message(observation)
    if note:
        content = f"{content}\n\n{note}"
    state.messages.append({"role": "user", "content": content})
    state.observation = observation
    state.attached_note = note
    state.observation_kind = (
        classify_observation(observation) if ctx.observation_shape else ""
    )
    _note_failure(state, return_code)
    if after.stop:
        state.stopped_by_guard = "consecutive_failures"
        ctx.logger.info("stopping: %s", after.note)
    record(state, ctx, "execute", **timing)
    if denied_site:
        state.node_trace[-1].update(recovery_action="suggest_pivot", recovery_site=denied_site)
    sync(state, ctx.harbor)
    return {
        "messages": state.messages,
        "guard": state.guard,
        "stopped_by_guard": state.stopped_by_guard,
        "node_trace": state.node_trace,
        "observation": state.observation,
        "observation_kind": state.observation_kind,
        "attached_note": state.attached_note,
        "identical_failures": state.identical_failures,
        "last_failed_command": state.last_failed_command,
        "progress_streak_mark": state.progress_streak_mark,
    }


def _note_failure(state: AgentState, return_code: int) -> None:
    """Count a run of the same failing command. A success clears it."""
    if return_code == 0:
        state.identical_failures = 0
        state.last_failed_command = ""
        state.progress_streak_mark = 0
        return
    if state.command == state.last_failed_command:
        state.identical_failures += 1
        return
    state.last_failed_command = state.command
    state.identical_failures = 1
    state.progress_streak_mark = 0
