"""Notice when the agent has stopped making progress.

Every failure in our baseline was a timeout, not a wrong answer, and the two
tasks we never solved were also the two most expensive (785k and 873k tokens
against 30k–280k for the ones we solve). The model doesn't know it is stuck —
it re-runs the same command, gets the same error, and reasons about it again.

This module is the "are we stuck?" check. It doesn't decide what to do next;
it hands the model a blunt observation about its own behaviour so the model can
change approach, and tells the agent loop when to stop paying for more turns.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

REPEAT_WARN_AT = 1
"""Warn as soon as the model reaches for a command it has already run."""

REPEAT_ABORT_AT = 3
"""Refuse a command the model has already run this many times."""

CONSECUTIVE_FAILURE_ABORT_AT = 8
"""Stop the task after this many failing commands in a row."""


class Attempt(BaseModel):
    """One executed command and how it went."""

    command: str
    return_code: int


class GuardVerdict(BaseModel):
    """What the guard wants the agent loop to do with the next command."""

    run: bool = True
    note: str | None = Field(
        default=None,
        description="Text to show the model instead of, or alongside, the output.",
    )
    stop: bool = False


class LoopGuard(BaseModel):
    """Tracks repeated commands and runs of failures within one task."""

    history: list[Attempt] = Field(default_factory=list)
    consecutive_failures: int = 0

    def _times_seen(self, command: str) -> int:
        return sum(1 for a in self.history if a.command == command)

    def before(self, command: str) -> GuardVerdict:
        """Called with the command the model wants to run next."""
        seen = self._times_seen(command)
        if seen >= REPEAT_ABORT_AT:
            return GuardVerdict(
                run=False,
                note=(
                    f"You have already run this exact command {seen} times and it has not "
                    "changed anything. It will not be run again. Do something "
                    "different: inspect a different file, use a different tool, or "
                    "question an assumption you have been treating as fact."
                ),
            )
        if seen >= REPEAT_WARN_AT:
            return GuardVerdict(
                run=True,
                note=(
                    f"Note: you have already run this exact command {seen} "
                    f"{'time' if seen == 1 else 'times'}. "
                    "If the output is the same again, change approach rather than "
                    "repeating it."
                ),
            )
        return GuardVerdict()

    def after(self, command: str, return_code: int) -> GuardVerdict:
        """Called with the result of a command that actually ran."""
        self.history.append(Attempt(command=command, return_code=return_code))
        if return_code == 0:
            self.consecutive_failures = 0
            return GuardVerdict()

        self.consecutive_failures += 1
        if self.consecutive_failures >= CONSECUTIVE_FAILURE_ABORT_AT:
            return GuardVerdict(
                stop=True,
                note=(
                    f"{self.consecutive_failures} commands in a row have failed. "
                    "Stopping this task rather than spending the remaining budget "
                    "on the same approach."
                ),
            )
        return GuardVerdict()
