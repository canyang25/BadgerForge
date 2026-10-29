"""Ask what changed, once a streak of identical failures or a block of turns has passed.

Off unless ``AGENT_PROGRESS_CHECK=1``. Plan 33: five sometimes-solved tasks
stick to one approach. The loop guard only catches the exact same command.
``node_trace`` has a ``progress`` row when this fires, which is how we know.
"""

from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.trace import record, sync
from agent.prompts import PROGRESS_MESSAGE
from agent.state import AgentState


def needs_progress(state: AgentState, ctx: GraphContext) -> bool:
    """True once per ``progress_every`` turns, and once per failure streak."""
    return bool(_progress_reasons(state, ctx))


def _progress_reasons(state: AgentState, ctx: GraphContext) -> list[str]:
    if not ctx.progress_check:
        return []
    periodic = (
        ctx.progress_every > 0
        and state.turns > 0
        and state.turns % ctx.progress_every == 0
        and state.progress_at_turn != state.turns
    )
    streak = (
        state.identical_failures >= 3
        and state.progress_streak_mark != state.identical_failures
    )
    reasons = []
    if periodic:
        reasons.append("periodic")
    if streak:
        reasons.append("identical_failures")
    return reasons


async def progress(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    ctx = runtime.context
    reasons = _progress_reasons(state, ctx)
    if ctx.progress_every > 0 and state.turns % ctx.progress_every == 0:
        state.progress_at_turn = state.turns
    if state.identical_failures >= 3:
        state.progress_streak_mark = state.identical_failures
    state.messages.append({"role": "user", "content": PROGRESS_MESSAGE})
    record(state, ctx, "progress")
    state.node_trace[-1].update(
        reasons=reasons,
        progress_every=ctx.progress_every,
        identical_failures=state.identical_failures,
    )
    ctx.logger.info("turn %d: progress check reasons=%s", state.turns, reasons)
    sync(state, ctx.harbor)
    return {
        "messages": state.messages,
        "node_trace": state.node_trace,
        "progress_at_turn": state.progress_at_turn,
        "progress_streak_mark": state.progress_streak_mark,
    }
