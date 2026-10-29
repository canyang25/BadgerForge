"""Replace dumps the model cannot read, and flag output that was cut.

Off unless ``AGENT_OBSERVATION_SHAPE=1``. Plan 8: summarize a binary or numeric
dump in code. Plan 29: when output is cut, say to use head, tail, grep, or a file.
"""

import re

from langgraph.runtime import Runtime

from agent.graph.context import GraphContext
from agent.graph.trace import record, sync
from agent.prompts import DUMP_NOTE, TRUNCATION_NOTE, observation_message
from agent.state import AgentState

_NUMERIC_ROWS = 8
_NONTEXT = 16
_ANSI_ESCAPE = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-_])"
)
_BINARY_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+")


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
    text = _ANSI_ESCAPE.sub("", observation)
    if "\x00" in text:
        return True
    return _nontext_count(text) >= _NONTEXT


def _nontext_count(text: str) -> int:
    return sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t")


def _looks_matrix(observation: str) -> bool:
    run = 0
    for line in _stdout(observation).splitlines():
        run = run + 1 if _numeric_row(line) else 0
        if run >= _NUMERIC_ROWS:
            return True
    return False


def _numeric_row(line: str) -> bool:
    parts = _ANSI_ESCAPE.sub("", line).split()
    if len(parts) < 4:
        return False
    for part in parts:
        try:
            float(part.strip(",[]()"))
        except ValueError:
            return False
    return True


def _stdout(observation: str) -> str:
    return _streams(observation)[0]


def _streams(observation: str) -> tuple[str, str]:
    """Read the stream labels emitted by run_shell without dropping either."""
    _, _, body = observation.partition("\n")
    if body.startswith("stdout:\n"):
        stdout, _, stderr = body[len("stdout:\n"):].partition("\nstderr:\n")
        return stdout, stderr
    if body.startswith("stderr:\n"):
        return "", body[len("stderr:\n"):]
    return body, ""


def _exit_line(observation: str) -> str:
    line = observation.split("\n", 1)[0]
    if line.startswith("exit code:") or line.startswith("[command did not complete"):
        return line
    return "exit code: 1"


def _summary(observation: str, kind: str) -> str:
    parts = [_exit_line(observation)]
    for name, text in zip(("stdout", "stderr"), _streams(observation)):
        if not text:
            continue
        if _looks_binary(text):
            text = _summarize_binary(text)
        if name == "stdout" and kind == "matrix":
            text = _summarize_tables(text)
        parts.append(f"{name}:\n{text}")
    return "\n".join(parts)


def _summarize_binary(text: str) -> str:
    """Suppress binary sections while retaining readable diagnostic text."""
    output = []
    binary = []
    for line in text.splitlines(keepends=True):
        clean = _ANSI_ESCAPE.sub("", line)
        if _nontext_count(clean):
            if _BINARY_CONTROL.sub("", clean).strip():
                output.append(_binary_summary(binary))
                binary = []
                output.append(_BINARY_CONTROL.sub("\ufffd", clean))
            else:
                binary.append(line)
        else:
            output.append(_binary_summary(binary))
            binary = []
            output.append(line)
    output.append(_binary_summary(binary))
    return "".join(output)


def _binary_summary(lines: list[str]) -> str:
    if not lines:
        return ""
    text = "".join(lines)
    nontext = _nontext_count(_ANSI_ESCAPE.sub("", text))
    suffix = "\n" if text.endswith("\n") else ""
    summary = (
        f"[binary data: {len(text)} characters, {nontext} non-text; not shown]"
        f"{suffix}"
    )
    if len(summary) <= len(text):
        return summary
    short = f"[binary data]{suffix}"
    return short if len(short) <= len(text) else f"\ufffd{suffix}"


def _summarize_tables(text: str) -> str:
    """Replace contiguous numeric runs, preserving labels and other text."""
    output = []
    rows = []
    for line in text.splitlines(keepends=True):
        if _numeric_row(line):
            rows.append(line)
        else:
            output.append(_table_summary(rows))
            rows = []
            output.append(line)
    output.append(_table_summary(rows))
    return "".join(output)


def _table_summary(rows: list[str]) -> str:
    if len(rows) < _NUMERIC_ROWS:
        return "".join(rows)
    first = rows[0].rstrip("\r\n")[:120]
    last = rows[-1].rstrip("\r\n")[:120]
    cols = len(_ANSI_ESCAPE.sub("", rows[0]).split())
    suffix = "\n" if rows[-1].endswith("\n") else ""
    summary = (
        f"[numeric table: {len(rows)} rows, about {cols} columns]\n"
        f"First row: {first}\nLast row: {last}\n"
        f"The full table was not sent.{suffix}"
    )
    original = "".join(rows)
    return summary if len(summary) < len(original) else original


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
