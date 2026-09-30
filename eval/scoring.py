"""Turn a Harbor jobs directory into the three numbers the leaderboard wants.

    leaderboard_score = tb_score - 0.01 * (total_tokens / 1_000_000)

Harbor writes one directory per trial, `<task>__<trial-id>/result.json`, under
`jobs/<job-id>/`. A task run several times has several trial directories; we
average reward and tokens per task, then aggregate across tasks, so repeated
trials cost nothing in the final numbers but show up as spread.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

TOKEN_PENALTY_PER_MILLION = 0.01


class Trial(BaseModel):
    """One `result.json`: a single attempt at a single task."""

    task: str
    reward: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    turns: int | None = None
    finished: bool = False

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @classmethod
    def from_result_json(cls, path: Path) -> "Trial":
        data = json.loads(path.read_text())
        agent = data.get("agent_result") or {}
        verifier = data.get("verifier_result") or {}
        metadata = agent.get("metadata") or {}
        return cls(
            task=path.parent.name.split("__")[0],
            reward=(verifier.get("rewards") or {}).get("reward") or 0.0,
            input_tokens=agent.get("n_input_tokens") or 0,
            output_tokens=agent.get("n_output_tokens") or 0,
            turns=metadata.get("turns"),
            finished=bool(metadata.get("finished")),
        )


class TaskSummary(BaseModel):
    """One task, averaged over however many trials it got."""

    task: str
    trials: int
    reward: float
    tokens: float
    reward_spread: float = Field(description="max reward - min reward across trials")
    token_spread: int = Field(description="max tokens - min tokens across trials")


class JobSummary(BaseModel):
    """What we report: score, tokens, and the leaderboard number."""

    tasks: list[TaskSummary]
    tb_score: float
    total_tokens: float
    leaderboard_score: float


def load_trials(job_dir: Path) -> list[Trial]:
    """Read every trial under a job directory (or several job directories)."""
    return sorted(
        (Trial.from_result_json(p) for p in job_dir.glob("*__*/result.json")),
        key=lambda t: t.task,
    )


def summarize(trials: list[Trial]) -> JobSummary:
    """Average per task, then aggregate. Empty input gives zeros, not an error."""
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
            )
        )

    tb_score = sum(t.reward for t in tasks) / len(tasks) if tasks else 0.0
    total_tokens = sum(t.tokens for t in tasks)
    penalty = TOKEN_PENALTY_PER_MILLION * (total_tokens / 1_000_000)
    return JobSummary(
        tasks=tasks,
        tb_score=tb_score,
        total_tokens=total_tokens,
        leaderboard_score=tb_score - penalty,
    )


def format_table(summary: JobSummary) -> str:
    """A table meant to be pasted into a PR description."""
    lines = [
        f"{'task':<28} {'trials':>6} {'reward':>7} {'tokens':>12} {'spread':>12}",
        "-" * 68,
    ]
    for t in summary.tasks:
        lines.append(
            f"{t.task:<28} {t.trials:>6} {t.reward:>7.2f} "
            f"{t.tokens:>12,.0f} {t.token_spread:>12,}"
        )
    lines += [
        "-" * 68,
        f"TB score:          {summary.tb_score:.4f}",
        f"Total tokens:      {summary.total_tokens:,.0f}",
        f"Leaderboard score: {summary.leaderboard_score:.4f}",
    ]
    return "\n".join(lines)
