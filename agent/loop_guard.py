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

import re
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

REPEAT_WARN_AT = 1
"""Warn as soon as the model reaches for a command it has already run."""

REPEAT_ABORT_AT = 3
"""Refuse a command the model has already run this many times."""

CONSECUTIVE_FAILURE_ABORT_AT = 8
"""Stop the task after this many failing commands in a row."""

DENIAL_STREAK = 3
_URL = re.compile(r"""https?://[^\s'"<>]+""", re.IGNORECASE)
_HTTP_STATUS = re.compile(
    r"\b(?:HTTP(?:/[\d.]+|[ \t]*Error)?[ \t:]+|status(?:[ \t]+code)?[ \t:=]+"
    r"|URL returned error:[ \t]*)([1-5]\d{2})\b",
    re.IGNORECASE,
)


def _denied_site(command: str, observation: str) -> str | None:
    """Identify one named site when the command reports only HTTP 403s."""
    if not observation.startswith("exit code:"):
        return None
    if set(_HTTP_STATUS.findall(observation)) != {"403"}:
        return None
    sites = set()
    for url in _URL.findall(command):
        try:
            host = urlsplit(url).hostname
        except ValueError:
            return None
        if not host or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", host):
            return None
        sites.add(host.removeprefix("www."))
    return next(iter(sites)) if len(sites) == 1 else None


class Attempt(BaseModel):
    """One executed command and how it went."""

    command: str
    return_code: int
    denied_site: str | None = None


class GuardVerdict(BaseModel):
    """What the guard wants the agent loop to do with the next command."""

    run: bool = True
    note: str | None = Field(
        default=None,
        description="Text to show the model instead of, or alongside, the output.",
    )
    stop: bool = False
    denied_site: str | None = None


class LoopGuard(BaseModel):
    """Tracks repeated commands and runs of failures within one task."""

    history: list[Attempt] = Field(default_factory=list)
    consecutive_failures: int = 0
    denial_retry_refused_at: int = -1

    def _times_seen(self, command: str) -> int:
        return sum(1 for a in self.history if a.command == command)

    def before(self, command: str, *, recover_denials: bool = False) -> GuardVerdict:
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
        if recover_denials:
            site = self.new_denial_streak()
            if (
                site
                and self.denial_retry_refused_at != len(self.history)
                and any(attempt.command == command for attempt in self.history[-DENIAL_STREAK:])
            ):
                self.denial_retry_refused_at = len(self.history)
                return GuardVerdict(
                    run=False,
                    note=(
                        f"Skipped this retry after repeated HTTP 403 from {site}. "
                        "Try a different source or a local approach."
                    ),
                    denied_site=site,
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

    def new_denial_streak(self) -> str | None:
        """Return the site exactly when its consecutive denials reach the threshold."""
        recent = self.history[-(DENIAL_STREAK + 1):]
        if len(recent) < DENIAL_STREAK:
            return None
        site = recent[-1].denied_site
        if site is None or any(attempt.denied_site != site for attempt in recent[-DENIAL_STREAK:]):
            return None
        return site if len(recent) == DENIAL_STREAK or recent[0].denied_site != site else None

    def after(self, command: str, return_code: int, *, observation: str = "") -> GuardVerdict:
        """Called with the result of a command that actually ran."""
        self.history.append(Attempt(
            command=command, return_code=return_code, denied_site=_denied_site(command, observation)
        ))
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
