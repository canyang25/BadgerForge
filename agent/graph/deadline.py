"""Send one reminder before a model call near the configured wall-time limit."""

import os
from time import monotonic

from agent.graph.context import GraphContext
from agent.graph.trace import record, sync
from agent.prompts import DEADLINE_MESSAGE
from agent.state import AgentState

RUN_BUDGET_SEC = int(os.environ.get("AGENT_RUN_BUDGET_SEC", "0"))
NOTICE_SEC = int(os.environ.get("AGENT_DEADLINE_NOTICE_SEC", "0"))


def add_deadline_notice(state: AgentState, ctx: GraphContext) -> None:
    if RUN_BUDGET_SEC <= 0 or NOTICE_SEC <= 0:
        return
    remaining = RUN_BUDGET_SEC - (monotonic() - ctx.started_at)
    if not 0 < remaining <= NOTICE_SEC:
        return
    if any(row["node"] == "deadline_notice" for row in state.node_trace):
        return

    message = DEADLINE_MESSAGE.format(remaining_seconds=int(remaining))
    state.messages.append({"role": "user", "content": message})
    record(state, ctx, "deadline_notice")
    state.node_trace[-1]["remaining_sec"] = round(remaining, 3)
    sync(state, ctx.harbor)
