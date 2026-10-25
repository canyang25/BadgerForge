"""Ask the model what to do next. This is the only node that spends tokens."""

from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.trace import record, sync
from agent.state import AgentState
from agent.tools import parse_action


async def call_model(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    ctx = runtime.context
    turns = state.turns + 1
    text, usage = await ctx.llm.chat(state.messages, temperature=state.next_temperature)
    bumped = state.next_temperature is not None
    state.turns = turns
    state.next_temperature = None
    state.n_input += int(usage.get("prompt_tokens") or 0)
    state.n_output += int(usage.get("completion_tokens") or 0)
    state.last_truncated = bool(ctx.llm.last_truncated)
    record(state, ctx, "call_model", usage)
    state.messages.append({"role": "assistant", "content": text})

    action = parse_action(text)
    state.action_kind = action.kind
    state.command = action.command
    if action.kind == "done":
        state.finished = True
    elif action.kind == "shell":
        # Count a command that follows a hotter sample even if the guard
        # later refuses to run it. That is what the loop counted.
        state.turns_without_action = 0
        if bumped:
            state.commands_after_bump += 1
    sync(state, ctx.harbor)
    return {
        "messages": state.messages,
        "turns": state.turns,
        "n_input": state.n_input,
        "n_output": state.n_output,
        "finished": state.finished,
        "turns_without_action": state.turns_without_action,
        "commands_after_bump": state.commands_after_bump,
        "next_temperature": state.next_temperature,
        "last_truncated": state.last_truncated,
        "action_kind": state.action_kind,
        "command": state.command,
        "node_trace": state.node_trace,
    }
