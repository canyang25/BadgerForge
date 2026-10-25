"""The main agent loop — this is where Harbor calls into your code.

How it works
============
Harbor orchestrates Terminal-Bench tasks. For each task it:
  1. Spins up a fresh Docker container with the task's source code and tests.
  2. Calls **your agent's** ``setup()`` (install tools if needed) and then
     ``run()`` (solve the task).
  3. After ``run()`` returns (or times out), Harbor runs the task's test suite
     against the container's final state to produce a reward (1.0 = pass).

This file implements ``BaselineAgent``, a minimal
`ReAct <https://arxiv.org/abs/2210.03629>`_ loop:

    ┌──────────────────────────────────────────────┐
    │  Send conversation (system prompt + history)  │
    │  to the LLM via HTTP (see llm.py)             │
    │                                               │
    │  Parse the LLM's response (see tools.py):     │
    │    ```bash ...```  → execute in container      │
    │    TASK_COMPLETE   → stop the loop             │
    │    anything else   → nudge the LLM to act      │
    │                                               │
    │  Append command output back as context          │
    │  Repeat up to MAX_TURNS                        │
    └──────────────────────────────────────────────┘

That loop is the LangGraph in ``agent/graph`` (``call_model``, ``nudge``,
``guard``, ``execute``). The decisions are the ones drawn above.
``context.metadata["node_trace"]`` records each node and the tokens it added.

The agent **never touches your host filesystem** — it can only run commands
inside the task's Docker container via ``environment.exec()``.

What to improve
===============
This baseline has no planning, no error recovery, no context-window
management, and no self-critique. Those are the levers that separate a
20% score from an 80% score. Ideas to explore:

- **Planning:** Have the LLM outline a multi-step plan before acting.
- **Context management:** Summarize or drop old turns so the conversation
  doesn't exceed the model's context window.
- **Error recovery:** Detect repeated failures and try a different approach.
- **Self-verification:** Run the task's tests before declaring done.
- **Tool use:** Give the LLM higher-level actions (read_file, write_file)
  instead of making it compose raw bash every turn.

Run it
======
::

    harbor run -d terminal-bench@2.0 \\
        --agent agent.agent:BaselineAgent \\
        -i fix-git

Environment variables
=====================
- ``AGENT_MAX_TURNS``  — max reasoning/action cycles per task (default: 100).
- ``AGENT_COMMAND_TIMEOUT_SEC`` — per-command timeout in seconds (default: 60).
- ``AGENT_PROGRESS_CHECK`` — ``1`` inserts a progress check every
  ``AGENT_PROGRESS_EVERY`` turns (default 10) and after 3 identical failures.
- ``AGENT_OBSERVATION_SHAPE`` — ``1`` summarizes binary or numeric dumps and
  tells the model when output was cut. Both are off unless set.
"""

import os

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from agent.graph import run_graph
from agent.graph.context import GraphContext
from agent.llm import LLMClient
from agent.loop_guard import LoopGuard
from agent.prompts import SYSTEM_PROMPT
from agent.state import AgentState

MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "100"))
MAX_TURNS_WITHOUT_ACTION = int(os.environ.get("AGENT_MAX_TURNS_WITHOUT_ACTION", "4"))
"""Give up after this many consecutive turns that produce no command.

A reasoning model that spends its whole output budget thinking returns nothing
usable, turn after turn. In our baseline one task emitted the same truncated
thought nine times in a row and then hit the task timeout, having spent 1M
tokens. Four strikes and we stop: the remaining budget buys nothing."""
COMMAND_TIMEOUT_SEC = int(os.environ.get("AGENT_COMMAND_TIMEOUT_SEC", "60"))
APT_WAIT_SEC = 120
APT_WAIT_COMMAND = (
    f"for _ in $(seq {APT_WAIT_SEC // 2}); do busy=0; "
    "for c in /proc/[0-9]*/comm; do "
    'case "$(cat "$c" 2>/dev/null)" in apt|apt-get|dpkg|unattended-upgr*) busy=1;; esac; '
    'done; [ "$busy" = 0 ] && exit 0; sleep 2; done; exit 0'
)
NO_COMMAND_TEMPERATURE = float(os.environ.get("AGENT_NO_COMMAND_TEMPERATURE", "0.7"))
PROGRESS_CHECK = os.environ.get("AGENT_PROGRESS_CHECK", "") == "1"
PROGRESS_EVERY = int(os.environ.get("AGENT_PROGRESS_EVERY", "10"))
OBSERVATION_SHAPE = os.environ.get("AGENT_OBSERVATION_SHAPE", "") == "1"
"""Temperature for the request after a reply that ended without a command
and wasn't cut off. Those replies announce a step ("Let's start by exploring
the environment.") and never take it; the wording drifts, the decision not to
act doesn't, until the agent gives up: 4 of 89 tasks in the 2026-10-07 full
run, 3 of 30 trials on the 10-08 slice. At 0.2 the same context gives nearly
the same replies (two portfolio-optimization trials produced the identical
four), so the next sample is warmer as well as nudged."""


class BaselineAgent(BaseAgent):
    """A minimal ReAct agent that solves tasks by issuing bash commands.

    Harbor discovers this class via the ``--agent`` CLI flag.
    It calls ``setup()`` once, then ``run()`` once per task. The class must
    implement all four methods below (``name``, ``version``, ``setup``,
    ``run``) — that's the Harbor BaseAgent contract.
    """

    @staticmethod
    def name() -> str:
        return "mlm26-baseline"

    def version(self) -> str | None:
        return "0.1.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        """Called once before ``run()``: wait for any apt/dpkg still running.

        Some images start an apt process that holds the dpkg lock for a while.
        In full run 3 that made the model's own installs fail in six trials.
        Waiting here (up to APT_WAIT_SEC, then carrying on regardless) costs
        nothing when the lock is free. Plain sh and /proc only: minimal images
        have no pgrep or fuser.
        """
        try:
            await environment.exec(command=APT_WAIT_COMMAND, timeout_sec=APT_WAIT_SEC + 30)
        except Exception as exc:  # never fail a task over this
            self.logger.info("apt wait skipped: %s", exc)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Solve the task. This is the main agent loop.

        Parameters
        ----------
        instruction : str
            The task description (e.g., "find the lost git changes and merge
            them into master"). This is what the LLM sees as the first user
            message.
        environment : BaseEnvironment
            The Docker container interface. The only way to interact with the
            task is ``environment.exec(command=..., timeout_sec=...)``, which
            returns an ``ExecResult`` with ``.stdout``, ``.stderr``, and
            ``.return_code``.
        context : AgentContext
            A mutable object where you report token usage and metadata.
            Harbor reads this after ``run()`` returns (or times out) to
            record stats in ``result.json``. **Update it every turn** so
            that even a timeout produces partial usage data.
        """
        llm = LLMClient(model_name=self.model_name)

        # The conversation is a plain list of OpenAI-format message dicts.
        # The system prompt (from prompts.py) tells the LLM how to behave;
        # the first user message is the task instruction from Harbor.
        # The graph updates ``context`` on every node, so a timeout still
        # leaves partial token counts.
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]
        await run_graph(
            AgentState(messages=messages, guard=LoopGuard()),
            GraphContext(
                llm=llm,
                environment=environment,
                logger=self.logger,
                harbor=context,
                max_turns=MAX_TURNS,
                max_turns_without_action=MAX_TURNS_WITHOUT_ACTION,
                command_timeout_sec=COMMAND_TIMEOUT_SEC,
                no_command_temperature=NO_COMMAND_TEMPERATURE,
                progress_check=PROGRESS_CHECK,
                progress_every=PROGRESS_EVERY,
                observation_shape=OBSERVATION_SHAPE,
            ),
        )
