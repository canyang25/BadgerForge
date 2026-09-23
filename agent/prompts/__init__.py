"""Prompt text, loaded from the .md files next to this module.

Prompts live in Markdown so they can be read and reviewed without scrolling
past Python quoting. Edit the .md files; nothing here needs to change.
"""

from pathlib import Path

_HERE = Path(__file__).parent

SYSTEM_PROMPT = (_HERE / "system.md").read_text().strip()
NUDGE_MESSAGE = (_HERE / "nudge.md").read_text().strip()


def observation_message(observation: str) -> str:
    """Format a command's output as the user message the model sees next."""
    return f"Command output:\n{observation}\n\nWhat is your next action?"
