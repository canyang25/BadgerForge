"""Turn a Harbor jobs directory into the three numbers the leaderboard wants.

    tokens_per_task   = total_tokens / n_tasks
    token_penalty     = min(0.01, 0.01 * tokens_per_task / 100_000_000)
    leaderboard_score = tb_score - token_penalty

The penalty is capped just under the value of one solved task (1/89), so
tokens only break ties between agents that pass the same number of tasks.
Rule as of 2026-10-07: kaggle.com/competitions/OpenAgent-Coding/overview/evaluation

Harbor writes one directory per trial, `<task>__<trial-id>/result.json`, under
`jobs/<job-id>/`. A task run several times has several trial directories; we
average reward and tokens per task, then aggregate across tasks, so repeated
trials cost nothing in the final numbers but show up as spread.

It also reports gateway health, because a slow or dropped gateway looks
exactly like a bad change in the score column. Seconds per turn and
connection failures are printed next to the numbers so nobody has to dig
through timestamps to tell the two apart.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

TOKEN_PENALTY_CAP = 0.01
TOKENS_PER_TASK_AT_CAP = 100_000_000

SLOW_TURN_SEC = 40.0
SLOW_OUTPUT_TOKENS_PER_SEC = 30.0
"""A trial is flagged as slow at the gateway only when both are true: more than
40 s per turn AND fewer than 30 output tokens per second.

Either test alone misfires. Seconds per turn flags healthy turns where the
model simply wrote a lot (a full 8k-token thought takes ~95 s at a normal
~90 tok/s). Tokens per second flags healthy trials that spend their time in
the container compiling code (sqlite-with-gcov runs at 7-14 tok/s). A slow
gateway trips both. Checked against all 135 trials we had on 2026-10-05: it
catches every trial from the known degraded windows and nothing from the
healthy post-#8 runs."""

INFRA_ERRORS = frozenset({"APIConnectionError", "APITimeoutError"})
"""Exceptions that mean the gateway failed, not the agent."""


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Trial(BaseModel):
    """One `result.json`: a single attempt at a single task."""

    task: str
    trial_id: str = ""
    reward: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    turns: int | None = None
    finished: bool = False
    seconds: float | None = None
    exception: str | None = None

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def seconds_per_turn(self) -> float | None:
        if self.seconds is None or not self.turns:
            return None
        return self.seconds / self.turns

    @property
    def output_tokens_per_sec(self) -> float | None:
        if not self.seconds:
            return None
        return self.output_tokens / self.seconds

    @property
    def slow(self) -> bool:
        spt, tps = self.seconds_per_turn, self.output_tokens_per_sec
        if spt is None or tps is None:
            return False
        return spt > SLOW_TURN_SEC and tps < SLOW_OUTPUT_TOKENS_PER_SEC

    @property
    def infra_error(self) -> bool:
        return self.exception in INFRA_ERRORS

    @classmethod
    def from_result_json(cls, path: Path) -> "Trial":
        data = json.loads(path.read_text())
        agent = data.get("agent_result") or {}
        verifier = data.get("verifier_result") or {}
        metadata = agent.get("metadata") or {}
        execution = data.get("agent_execution") or {}
        start = _parse_time(execution.get("started_at"))
        end = _parse_time(execution.get("finished_at"))
        return cls(
            task=path.parent.name.split("__")[0],
            trial_id=path.parent.name,
            reward=(verifier.get("rewards") or {}).get("reward") or 0.0,
            input_tokens=agent.get("n_input_tokens") or 0,
            output_tokens=agent.get("n_output_tokens") or 0,
            turns=metadata.get("turns"),
            finished=bool(metadata.get("finished")),
            seconds=(end - start).total_seconds() if start and end else None,
            exception=(data.get("exception_info") or {}).get("exception_type"),
        )


class TaskSummary(BaseModel):
    """One task, averaged over however many trials it got."""

    task: str
    trials: int
    reward: float
    tokens: float
    reward_spread: float = Field(description="max reward - min reward across trials")
    token_spread: int = Field(description="max tokens - min tokens across trials")
    sec_per_turn: float | None = Field(
        default=None, description="median seconds per turn across trials"
    )


class JobSummary(BaseModel):
    """What we report: score, tokens, and the leaderboard number."""

    tasks: list[TaskSummary]
    tb_score: float
    total_tokens: float
    tokens_per_task: float = 0.0
    leaderboard_score: float
    median_sec_per_turn: float | None = None
    slow: list[Trial] = Field(default_factory=list)
    infra_failures: list[Trial] = Field(default_factory=list)
    dropped_infra: bool = False


def load_trials(job_dir: Path) -> list[Trial]:
    """Read every trial under a job directory (or several job directories)."""
    return sorted(
        (Trial.from_result_json(p) for p in job_dir.glob("*__*/result.json")),
        key=lambda t: t.task,
    )


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def summarize(trials: list[Trial], drop_infra: bool = False) -> JobSummary:
    """Average per task, then aggregate. Empty input gives zeros, not an error.

    Trials that failed on the gateway connection count as 0 by default, as
    they would in an official run. `drop_infra=True` leaves them out — for
    comparing two dev-slice runs, where a dropped VPN says nothing about the
    agent. Either way they are listed in the summary.
    """
    infra = [t for t in trials if t.infra_error]
    if drop_infra:
        trials = [t for t in trials if not t.infra_error]

    by_task: dict[str, list[Trial]] = {}
    for trial in trials:
        by_task.setdefault(trial.task, []).append(trial)

    tasks: list[TaskSummary] = []
    for task, group in sorted(by_task.items()):
        rewards = [t.reward for t in group]
        tokens = [t.tokens for t in group]
        tasks.append(
            TaskSummary(
                task=task,
                trials=len(group),
                reward=sum(rewards) / len(rewards),
                tokens=sum(tokens) / len(tokens),
                reward_spread=max(rewards) - min(rewards),
                token_spread=max(tokens) - min(tokens),
                sec_per_turn=_median(
                    [t.seconds_per_turn for t in group if t.seconds_per_turn is not None]
                ),
            )
        )

    tb_score = sum(t.reward for t in tasks) / len(tasks) if tasks else 0.0
    total_tokens = sum(t.tokens for t in tasks)
    # Divide by the tasks we ran, not 89, so a dev slice gets the same
    # per-task number a full run would.
    tokens_per_task = total_tokens / len(tasks) if tasks else 0.0
    penalty = TOKEN_PENALTY_CAP * min(1.0, tokens_per_task / TOKENS_PER_TASK_AT_CAP)
    return JobSummary(
        tasks=tasks,
        tb_score=tb_score,
        total_tokens=total_tokens,
        tokens_per_task=tokens_per_task,
        leaderboard_score=tb_score - penalty,
        median_sec_per_turn=_median(
            [t.seconds_per_turn for t in trials if t.seconds_per_turn is not None]
        ),
        slow=sorted((t for t in trials if t.slow), key=lambda t: -(t.seconds_per_turn or 0)),
        infra_failures=infra,
        dropped_infra=drop_infra,
    )


def format_table(summary: JobSummary) -> str:
    """A table meant to be pasted into a PR description."""
    width = 76
    lines = [
        f"{'task':<28} {'trials':>6} {'reward':>7} {'tokens':>12} {'spread':>12} {'s/turn':>6}",
        "-" * width,
    ]
    for t in summary.tasks:
        spt = f"{t.sec_per_turn:>6.0f}" if t.sec_per_turn is not None else f"{'-':>6}"
        lines.append(
            f"{t.task:<28} {t.trials:>6} {t.reward:>7.2f} "
            f"{t.tokens:>12,.0f} {t.token_spread:>12,} {spt}"
        )
    lines += [
        "-" * width,
        f"TB score:          {summary.tb_score:.5f}",
        f"Total tokens:      {summary.total_tokens:,.0f}",
        f"Tokens per task:   {summary.tokens_per_task:,.0f}",
        f"Leaderboard score: {summary.leaderboard_score:.5f}",
        "",
    ]
    lines += _health_lines(summary)
    return "\n".join(lines)


def _health_lines(summary: JobSummary) -> list[str]:
    """Gateway health, printed under the numbers it can distort."""
    median = summary.median_sec_per_turn
    lines = [
        f"Gateway:           median {median:.0f} s/turn" if median is not None
        else "Gateway:           no timing data"
    ]
    if not summary.slow and not summary.infra_failures:
        lines[0] += ", no slow trials, no connection failures"
        return lines

    if summary.slow:
        lines.append(
            f"WARNING: {len(summary.slow)} trial(s) slow at the gateway "
            f"(>{SLOW_TURN_SEC:.0f} s/turn and <{SLOW_OUTPUT_TOKENS_PER_SEC:.0f} output tok/s). "
            "The gateway may explain these, not the agent:"
        )
        for t in summary.slow:
            lines.append(
                f"  {t.trial_id:<36} {t.seconds_per_turn:>5.0f} s/turn "
                f"{t.output_tokens_per_sec:>5.1f} tok/s  "
                f"{t.turns} turns  reward {t.reward:.0f}  {t.exception or ''}".rstrip()
            )

    if summary.infra_failures:
        n = len(summary.infra_failures)
        if summary.dropped_infra:
            lines.append(
                f"Dropped {n} trial(s) that failed on the gateway connection. "
                "Re-run them to keep the trial count per task even:"
            )
        else:
            lines.append(
                f"WARNING: {n} trial(s) failed on the gateway connection and count "
                "as 0. Re-run them, or pass --drop-infra-errors to leave them out:"
            )
        for t in summary.infra_failures:
            lines.append(f"  {t.trial_id:<36} {t.exception}")
    return lines
