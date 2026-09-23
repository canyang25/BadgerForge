"""Action parsing and command execution.

This file is the bridge between the LLM's text output and the Docker
container. It handles two things:

1. **Parsing** — Extracting a structured ``Action`` from the LLM's
   free-text response. The baseline protocol is intentionally simple so
   that even small local models (~7B) can follow it reliably:
   - A fenced ``bash`` code block → run that command in the container.
   - The literal string ``TASK_COMPLETE`` → stop the loop.
   - Anything else → the LLM didn't follow the protocol; agent.py will
     send a nudge message asking it to try again.

2. **Execution** — Running the parsed command inside the task's Docker
   container via Harbor's ``environment.exec()`` and formatting the
   stdout/stderr/exit-code into a string the LLM can read.

Output truncation
=================
Commands can produce megabytes of output (e.g., ``find /``). Feeding all of
that into the conversation would blow the model's context window. So
``run_shell()`` truncates long output to ``MAX_OBSERVATION_CHARS``, keeping
the first and last halves with a "[N characters omitted]" marker in between.
This is a blunt strategy — smarter truncation (e.g., keeping error lines,
tail-only, or summarizing) is a good improvement target.

Improvement ideas
=================
- Add richer action types (read_file, write_file, search) so the LLM
  doesn't have to compose raw bash for common operations.
- Parse multiple code blocks and execute them sequentially.
- Detect and break out of repeated-command loops.
- Smarter truncation: prioritize stderr, keep the last N lines, etc.
"""

import re
from dataclasses import dataclass

from harbor.environments.base import BaseEnvironment

CODE_BLOCK_RE = re.compile(r"```(?:bash|sh|shell)?\s*\n(.*?)```", re.DOTALL)
"""Matches a Markdown fenced code block tagged as bash/sh/shell (or untagged).
The captured group (1) is everything between the opening and closing fences."""

DONE_MARKER = "TASK_COMPLETE"
"""The literal string the LLM must emit (outside a code block) to signal
that it believes the task is finished."""

MAX_OBSERVATION_CHARS = 6000
"""Maximum characters to keep from a command's combined output. Longer
output is truncated to the first and last halves with an omission notice."""


@dataclass
class Action:
    """A single action parsed from the LLM's response.

    Attributes
    ----------
    kind : str
        One of ``"shell"`` (run a command), ``"done"`` (task complete),
        or ``"none"`` (no valid action found — LLM didn't follow protocol).
    command : str
        The bash command to execute. Only meaningful when ``kind == "shell"``.
    """

    kind: str
    command: str = ""


def parse_action(text: str) -> Action:
    """Extract a single action from the LLM's response text.

    Precedence: a code block wins over a ``TASK_COMPLETE`` mention, so the
    model can discuss finishing without accidentally terminating.

    Parameters
    ----------
    text : str
        The raw text content of the LLM's response.

    Returns
    -------
    Action
        The parsed action. ``kind`` is ``"shell"`` if a bash block was found,
        ``"done"`` if TASK_COMPLETE was found (and no code block), or
        ``"none"`` if neither was present.
    """
    match = CODE_BLOCK_RE.search(text)
    if match:
        command = match.group(1).strip()
        if command:
            return Action("shell", command)
    if DONE_MARKER in text:
        return Action("done")
    return Action("none")


def _truncate(text: str) -> str:
    """Truncate long text, keeping the first and last halves."""
    if len(text) <= MAX_OBSERVATION_CHARS:
        return text
    half = MAX_OBSERVATION_CHARS // 2
    omitted = len(text) - MAX_OBSERVATION_CHARS
    return f"{text[:half]}\n... [{omitted} characters omitted] ...\n{text[-half:]}"


async def run_shell(
    environment: BaseEnvironment, command: str, timeout_sec: int
) -> str:
    """Execute a bash command in the task's Docker container.

    Parameters
    ----------
    environment : BaseEnvironment
        Harbor's container interface. The key method is
        ``environment.exec(command=..., timeout_sec=...)``, which returns
        an ``ExecResult`` with ``.stdout``, ``.stderr``, and ``.return_code``.
    command : str
        The bash command string to run (can be multi-line).
    timeout_sec : int
        Maximum seconds to wait before killing the command.

    Returns
    -------
    str
        A formatted string containing the exit code, stdout, and stderr
        (each truncated to ``MAX_OBSERVATION_CHARS``). This string is what
        gets fed back to the LLM as the command's "observation."
    """
    try:
        result = await environment.exec(command=command, timeout_sec=timeout_sec)
    except Exception as exc:
        return f"[command did not complete: {exc}]"

    parts = [f"exit code: {result.return_code}"]
    if result.stdout:
        parts.append(f"stdout:\n{_truncate(result.stdout)}")
    if result.stderr:
        parts.append(f"stderr:\n{_truncate(result.stderr)}")
    if not result.stdout and not result.stderr:
        parts.append("(no output)")
    return "\n".join(parts)
