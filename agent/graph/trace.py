"""Per-node log line and the trace Harbor stores on the context.

Tokens are attributed to the node that spent them. Today only ``call_model``
spends any; the other nodes record a zero so a later planning node can show
up in the same list. This stays on the process: plan.md leaves LangSmith off
until the team agrees to send transcripts out.
"""

from asyncio import CancelledError
from contextlib import contextmanager
from time import monotonic

from harbor.models.agent.context import AgentContext

from agent.graph.context import GraphContext
from agent.state import AgentState


@contextmanager
def measure_step(ctx: GraphContext, node: str, turn: int):
    """Time an external wait and retain its elapsed time if the run ends there."""
    started = monotonic()
    timing = {}
    try:
        yield timing
    except (CancelledError, Exception) as exc:
        elapsed = round(monotonic() - started, 3)
        if ctx.harbor.metadata is None:
            ctx.harbor.metadata = {}
        ctx.harbor.metadata["interrupted_step"] = {
            "node": node, "turn": turn, "elapsed_sec": elapsed, "exception": type(exc).__name__
        }
        ctx.logger.info("interrupted node=%s turn=%d elapsed_sec=%.3f", node, turn, elapsed)
        raise
    else:
        timing["elapsed_sec"] = round(monotonic() - started, 3)


def record(
    state: AgentState, ctx: GraphContext, node: str, usage: dict | None = None,
    *, elapsed_sec: float | None = None,
) -> None:
    """Append one trace row and log this node's token usage and optional timing."""
    prompt = int((usage or {}).get("prompt_tokens") or 0)
    completion = int((usage or {}).get("completion_tokens") or 0)
    row = {
        "node": node,
        "turn": state.turns,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
    }
    timing = ""
    if elapsed_sec is not None:
        row["elapsed_sec"] = elapsed_sec
        timing = f" elapsed_sec={elapsed_sec:.3f}"
    state.node_trace.append(row)
    ctx.logger.info(
        "node=%s turn=%d prompt_tokens=%d completion_tokens=%d%s",
        node,
        state.turns,
        prompt,
        completion,
        timing,
    )


def sync(state: AgentState, harbor: AgentContext) -> None:
    """Copy counters onto Harbor's context. Same keys the loop used to write.

    LangGraph hands each node its own copy of ``messages`` and ``node_trace``,
    so the dict has to point at this node's lists or the trace stops at the
    previous step.
    """
    harbor.n_input_tokens = state.n_input
    harbor.n_output_tokens = state.n_output
    meta = harbor.metadata
    if meta is None:
        meta = {}
        harbor.metadata = meta
    meta["turns"] = state.turns
    meta["finished"] = state.finished
    meta["stopped_by_guard"] = state.stopped_by_guard
    meta["no_command_replies"] = state.no_command_replies
    meta["commands_after_bump"] = state.commands_after_bump
    meta["messages"] = state.messages
    meta["node_trace"] = state.node_trace
    if state.stop_reason is not None:
        meta["stop_reason"] = state.stop_reason
