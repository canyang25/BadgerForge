"""Scoring maths, checked against a fixture of real Harbor output."""

from pathlib import Path

import pytest

from eval.scoring import TOKEN_PENALTY_CAP, Trial, load_trials, summarize

FIXTURE = Path(__file__).parent / "fixtures" / "job"


@pytest.fixture
def summary():
    return summarize(load_trials(FIXTURE))


def test_finds_every_trial():
    assert len(load_trials(FIXTURE)) == 3


def test_repeated_trials_average_into_one_task(summary):
    regex = next(t for t in summary.tasks if t.task == "regex-log")
    assert regex.trials == 2
    assert regex.reward == 1.0
    # (620,274 + 852,317) / 2
    assert regex.tokens == pytest.approx(736_295.5)


def test_spread_exposes_run_to_run_variance(summary):
    regex = next(t for t in summary.tasks if t.task == "regex-log")
    assert regex.reward_spread == 0.0
    assert regex.token_spread == 232_043


def test_tb_score_is_mean_over_tasks_not_trials(summary):
    # One task passes, one fails: 0.5, even though 2 of 3 trials passed.
    assert summary.tb_score == pytest.approx(0.5)


def test_leaderboard_score_subtracts_the_per_task_token_penalty(summary):
    expected_tokens = 736_295.5 + 128_000
    assert summary.total_tokens == pytest.approx(expected_tokens)
    assert summary.tokens_per_task == pytest.approx(expected_tokens / 2)
    assert summary.leaderboard_score == pytest.approx(
        0.5 - 0.01 * (expected_tokens / 2) / 100_000_000
    )


def test_token_penalty_is_capped_below_one_solved_task():
    huge = Trial(task="a", reward=1.0, input_tokens=5_000_000_000)
    assert summarize([huge]).leaderboard_score == pytest.approx(1.0 - 0.01)
    assert TOKEN_PENALTY_CAP < 1 / 89


def test_empty_job_dir_is_not_an_error(tmp_path):
    empty = summarize(load_trials(tmp_path))
    assert empty.tasks == []
    assert empty.tb_score == 0.0
    assert empty.leaderboard_score == 0.0
