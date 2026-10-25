"""Per-node log line and the trace Harbor stores on the context.

Tokens are attributed to the node that spent them. Today only ``call_model``
spends any; the other nodes record a zero so a later planning node can show
up in the same list. This stays on the process: plan.md leaves LangSmith off
until the team agrees to send transcripts out.
"""

from harbor.models.agent.context import AgentContext

from agent.graph.context import GraphContext
from agent.state import AgentState


def record(
    state: AgentState, ctx: GraphContext, node: str, usage: dict | None = None
) -> None:
    """Append one trace row and log the token delta for this node."""
    prompt = int((usage or {}).get("prompt_tokens") or 0)
    completion = int((usage or {}).get("completion_tokens") or 0)
    state.node_trace.append(
        {
            "node": node,
            "turn": state.turns,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
        }
    )
    ctx.logger.info(
        "node=%s turn=%d prompt_tokens=%d completion_tokens=%d",
        node,
        state.turns,
        prompt,
        completion,
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
