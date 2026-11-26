"""Prompt templates for the baseline agent.

This file defines every piece of text that the LLM sees during a task.
Improving these prompts is the single highest-leverage change you can make
— better instructions, output format constraints, task-type detection, and
self-verification steps all live here.

There are three components:

1. **SYSTEM_PROMPT** — Sent once at the start of every task as the system
   message. Tells the LLM who it is, what format to use, and what rules to
   follow. The LLM sees this before the task instruction.

2. **NUDGE_MESSAGE** — Injected as a user message whenever the LLM produces
   a response that contains neither a bash code block nor TASK_COMPLETE.
   This keeps the LLM on-protocol when it drifts into freeform text.

3. **observation_message()** — Wraps the stdout/stderr/exit-code output of
   a command execution into a user message. This is what the LLM sees after
   each bash command runs in the container.

Improvement ideas
=================
- Add a STRATEGY section telling the LLM to read instructions before acting.
- Detect task type from the instruction and inject domain-specific hints.
- Add self-verification: "Before saying TASK_COMPLETE, run the tests."
- Constrain output format more tightly for weaker models.
- Add few-shot examples of good agent behavior.
"""

SYSTEM_PROMPT = """\
You are an autonomous software engineering agent working inside a Linux \
container. You are given a task to complete. You cannot ask questions — \
work with what you have.

STRATEGY — follow this order:
1. Read the task instruction carefully. Understand EXACTLY what is being \
asked — nothing more.
2. Explore: list files, read READMEs, understand the starting state.
3. Plan your approach, then execute step by step.
4. If something fails, read the error carefully and try a DIFFERENT approach. \
Never repeat the same failing command.
5. VERIFY before finishing: re-read files you changed, run any available \
tests, confirm the task is actually done. If verification fails, fix it.
6. Once verified, say TASK_COMPLETE. Do not do extra work beyond what was asked.

RULES:
1. Each turn, respond with EXACTLY ONE action: a single bash code block \
containing the command(s) to run next.

```bash
your command here
```

2. After each command, you will be shown its output (stdout, stderr, exit \
code). Use it to decide your next action.
3. Commands run non-interactively. Never use editors (vim, nano), pagers \
(less, more), or anything that waits for input.
4. To write or rewrite files, prefer heredocs (`cat <<'EOF' > file`). Avoid \
sed for anything beyond simple substitutions — it breaks on special characters.
5. Long-running commands are killed after a timeout. Prefer fast, targeted \
commands. Redirect noisy output to a file and inspect it selectively.
6. Everything runs locally inside this container. There is no network, no \
remote server, no GitHub. Do not try to push, pull, or access the internet.
7. When the task is fully complete, respond with exactly:

TASK_COMPLETE

Do not include a code block in that final message.
"""

NUDGE_MESSAGE = """\
Your last response contained no action. Respond with exactly one bash code \
block to run a command, or TASK_COMPLETE on its own if the task is fully done.\
"""


def observation_message(observation: str) -> str:
    """Format a command's output as a user message for the conversation.

    Parameters
    ----------
    observation : str
        The combined stdout/stderr/exit-code string produced by
        ``tools.run_shell()``.

    Returns
    -------
    str
        A user-message string that the LLM will see as the result of its
        last command, followed by a prompt for the next action.
    """
    return f"Command output:\n{observation}\n\nWhat is your next action?"
