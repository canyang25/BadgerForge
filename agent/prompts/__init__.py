"""Prompt text, loaded from the .md files next to this module.

Prompts live in Markdown so they can be read and reviewed without scrolling
past Python quoting. Edit the .md files; nothing here needs to change.
"""

from pathlib import Path

_HERE = Path(__file__).parent

SYSTEM_PROMPT = (_HERE / "system.md").read_text().strip()
NUDGE_MESSAGE = (_HERE / "nudge.md").read_text().strip()
ACT_NUDGE_MESSAGE = (_HERE / "nudge_act.md").read_text().strip()
OVERRUN_NOTES_TEMPLATE = (_HERE / "overrun_notes.md").read_text().strip()
SUBMIT_CHECK_MESSAGE = (_HERE / "submit_check.md").read_text().strip()
"""The answer to the first TASK_COMPLETE when the submit check is on (adapted
from Badger Agents)."""
TIME_RULE = (_HERE / "time_rule.md").read_text().strip()
"""Added to the system prompt when time awareness is on (adapted from Badger Agents)."""
CLOCK_TEMPLATE = "[time used: {minutes} min; the limit is unknown and may be as short as 15 min]"
TIME_NUDGE_MESSAGE = (
    "10 minutes used. If the required output isn't written yet, write your best version now, "
    "then keep improving it."
)
"""Appended to the nudge after a cut-off reply when overrun recovery is on
(wording adapted from Badger Agents)."""


def observation_message(observation: str) -> str:
    """Format a command's output as the user message the model sees next."""
    return f"Command output:\n{observation}\n\nWhat is your next action?"
