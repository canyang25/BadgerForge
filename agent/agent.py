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
"""

import os

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from agent.llm import LLMClient
from agent.loop_guard import LoopGuard
from agent.prompts import NUDGE_MESSAGE, SYSTEM_PROMPT, observation_message
from agent.tools import parse_action, parse_exit_code, run_shell

MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "100"))
MAX_TURNS_WITHOUT_ACTION = int(os.environ.get("AGENT_MAX_TURNS_WITHOUT_ACTION", "4"))
"""Give up after this many consecutive turns that produce no command.

A reasoning model that spends its whole output budget thinking returns nothing
usable, turn after turn. In our baseline one task emitted the same truncated
thought nine times in a row and then hit the task timeout, having spent 1M
tokens. Four strikes and we stop: the remaining budget buys nothing."""
COMMAND_TIMEOUT_SEC = int(os.environ.get("AGENT_COMMAND_TIMEOUT_SEC", "60"))

RECOVERY_EFFORT = os.environ.get("AGENT_RECOVERY_EFFORT", "medium").strip()
"""Reasoning effort for the one turn after a truncated turn that gave no command.

Truncation is sticky. Across 1,902 turns of healthy runs, 13% were cut off
mid-thought, but 47% of the turns right after a cut-off were cut off too. Each
costs ~95 s and a strike toward MAX_TURNS_WITHOUT_ACTION, and four in a row
ends the task before a command has run. Dropping effort for a single turn asks
for a command instead of another full think; the next turn goes back to the
default. Running at medium throughout cost score (0.76 vs 0.86), which is why
this is one turn only. "off" disables it."""


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
        """Called once before ``run()``. Install tools inside the container.

        The baseline needs nothing, but if your agent relies on tools like
        ripgrep, jq, or a custom script inside the container, install them
        here via ``environment.exec(command="apt-get install -y ...")``.

        Note: finale tasks may have **no network access** inside the
        container, so anything you install here must not require downloads.
        """
        pass

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
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]

        guard = LoopGuard()
        n_input = 0
        n_output = 0
        turns = 0
        finished = False
        turns_without_action = 0
        stop_reason = None
        recover_next = False
        recovery_turns = 0
        recovery_actions = 0
        stopped_by_guard = None

        for _ in range(MAX_TURNS):
            turns += 1

            # 1. Ask the LLM what to do next. After a truncated turn with no
            # command, ask with lower effort for this one turn (see
            # RECOVERY_EFFORT).
            effort = None
            if recover_next and RECOVERY_EFFORT not in ("", "off", "none"):
                effort = RECOVERY_EFFORT
            text, usage = await llm.chat(messages, reasoning_effort=effort)
            n_input += usage.get("prompt_tokens", 0)
            n_output += usage.get("completion_tokens", 0)

            # Update context every turn (not just at the end) so that if
            # Harbor kills us for a timeout, partial stats are still saved.
            context.n_input_tokens = n_input
            context.n_output_tokens = n_output
            context.metadata = {
                "turns": turns,
                "finished": finished,
                "stopped_by_guard": stopped_by_guard,
                "recovery_turns": recovery_turns,
                "recovery_actions": recovery_actions,
                "messages": messages,
            }

            messages.append({"role": "assistant", "content": text})

            # 2. Parse the response into an action (see tools.py).
            action = parse_action(text)

            if effort:
                recovery_turns += 1
                if action.kind != "none":
                    recovery_actions += 1
                context.metadata["recovery_turns"] = recovery_turns
                context.metadata["recovery_actions"] = recovery_actions
            recover_next = llm.last_truncated and action.kind == "none"

            if action.kind == "done":
                finished = True
                context.metadata["finished"] = True
                break

            if action.kind == "none":
                # The LLM didn't produce a bash block or TASK_COMPLETE.
                turns_without_action += 1
                if turns_without_action >= MAX_TURNS_WITHOUT_ACTION:
                    stop_reason = "no_action"
                    context.metadata["stop_reason"] = stop_reason
                    self.logger.info(
                        "stopping after %d turns with no command", turns_without_action
                    )
                    break
                # Nudge it back on-protocol.
                messages.append({"role": "user", "content": NUDGE_MESSAGE})
                continue

            turns_without_action = 0

            # 3. Ask the loop guard whether this command is worth running.
            verdict = guard.before(action.command)
            if not verdict.run:
                self.logger.info("turn %d: refused repeat: %s", turns, action.command[:120])
                messages.append({"role": "user", "content": verdict.note})
                continue

            # 4. Execute the command inside the task's Docker container.
            self.logger.info("turn %d: %s", turns, action.command[:200])
            observation = await run_shell(
                environment, action.command, timeout_sec=COMMAND_TIMEOUT_SEC
            )
            after = guard.after(action.command, parse_exit_code(observation))

            # 5. Feed the output back to the LLM as context for the next turn.
            note = verdict.note or after.note
            content = observation_message(observation)
            if note:
                content = f"{content}\n\n{note}"
            messages.append({"role": "user", "content": content})

            if after.stop:
                stopped_by_guard = "consecutive_failures"
                context.metadata["stopped_by_guard"] = stopped_by_guard
                self.logger.info("stopping: %s", after.note)
                break
