"""Replace dumps the model cannot read, and flag output that was cut.

Off unless ``AGENT_OBSERVATION_SHAPE=1``. Plan 8: summarize a binary or numeric
dump in code. Plan 29: when output is cut, say to use head, tail, grep, or a file.
"""

from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.trace import record, sync
from agent.prompts import DUMP_NOTE, TRUNCATION_NOTE, observation_message
from agent.state import AgentState

_NUMERIC_ROWS = 8
_NONTEXT = 16


def classify_observation(observation: str) -> str:
    """``binary``, ``matrix``, ``truncated``, or ``""`` when the text can stand."""
    if _looks_binary(observation):
        return "binary"
    if _looks_matrix(observation):
        return "matrix"
    if "characters omitted" in observation:
        return "truncated"
    return ""


def shape_message(
    message: str, observation: str, kind: str, attached_note: str | None
) -> str:
    """The user message the model should see instead of the raw observation."""
    if kind == "truncated":
        if TRUNCATION_NOTE in message:
            return message
        return f"{message}\n\n{TRUNCATION_NOTE}"

    content = observation_message(_summary(observation, kind))
    content = f"{content}\n\n{DUMP_NOTE}"
    if "characters omitted" in observation:
        content = f"{content}\n\n{TRUNCATION_NOTE}"
    if attached_note:
        content = f"{content}\n\n{attached_note}"
    return content


def _looks_binary(observation: str) -> bool:
    if "\x00" in observation:
        return True
    nontext = sum(1 for char in observation if ord(char) < 32 and char not in "\n\r\t")
    return nontext >= _NONTEXT


def _looks_matrix(observation: str) -> bool:
    rows = [line for line in _stdout(observation).splitlines() if _numeric_row(line)]
    return len(rows) >= _NUMERIC_ROWS


def _numeric_row(line: str) -> bool:
    parts = line.split()
    if len(parts) < 4:
        return False
    numbers = 0
    for part in parts:
        try:
            float(part.strip(","))
        except ValueError:
            continue
        numbers += 1
    return numbers >= 4 and numbers / len(parts) >= 0.8


def _stdout(observation: str) -> str:
    if "stdout:\n" not in observation:
        return ""
    rest = observation.split("stdout:\n", 1)[1]
    if "\nstderr:\n" in rest:
        rest = rest.split("\nstderr:\n", 1)[0]
    return rest


def _exit_line(observation: str) -> str:
    line = observation.split("\n", 1)[0]
    if line.startswith("exit code:") or line.startswith("[command did not complete"):
        return line
    return "exit code: 1"


def _summary(observation: str, kind: str) -> str:
    exit_line = _exit_line(observation)
    if kind == "binary":
        nontext = sum(
            1 for char in observation if ord(char) < 32 and char not in "\n\r\t"
        )
        return (
            f"{exit_line}\n"
            f"stdout/stderr look like binary data ({len(observation)} characters, "
            f"{nontext} non-text). Not shown."
        )
    rows = [line for line in _stdout(observation).splitlines() if _numeric_row(line)]
    first = rows[0][:120] if rows else ""
    last = rows[-1][:120] if rows else ""
    cols = len(first.split()) if first else 0
    return (
        f"{exit_line}\n"
        f"stdout looks like a numeric table: {len(rows)} rows, about {cols} columns.\n"
        f"First row: {first}\n"
        f"Last row: {last}\n"
        "The full table was not sent."
    )


async def shape(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    ctx = runtime.context
    message = state.messages[-1]["content"]
    state.messages[-1] = {
        "role": "user",
        "content": shape_message(
            message, state.observation, state.observation_kind, state.attached_note
        ),
    }
    record(state, ctx, "shape")
    ctx.logger.info("turn %d: shaped %s output", state.turns, state.observation_kind)
    sync(state, ctx.harbor)
    return {"messages": state.messages, "node_trace": state.node_trace}
