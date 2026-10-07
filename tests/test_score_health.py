"""Gateway health in the score report.

A dropped or slow gateway looks exactly like a bad change in the score
column. These cases are modelled on real trials from 2026-10-05.
"""

from datetime import datetime, timedelta, timezone
import json

import pytest

from eval.scoring import format_table, load_trials, summarize

START = datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)


def write_trial(job, name, *, reward=1.0, turns=20, seconds=300.0,
                output_tokens=20_000, exception=None):
    d = job / name
    d.mkdir(parents=True)
    data = {
        "verifier_result": {"rewards": {"reward": reward}} if reward is not None else None,
        "agent_result": {
            "n_input_tokens": 50_000,
            "n_output_tokens": output_tokens,
            "metadata": {"turns": turns},
        },
    }
    if seconds is not None:
        data["agent_execution"] = {
            "started_at": START.isoformat().replace("+00:00", "Z"),
            "finished_at": (START + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
        }
    if exception:
        data["exception_info"] = {"exception_type": exception}
    (d / "result.json").write_text(json.dumps(data))


@pytest.fixture
def job(tmp_path):
    # A normal trial: 15 s/turn, ~67 output tok/s.
    write_trial(tmp_path, "normal__a")
    # Long thinking, not a slow gateway: 4 turns of ~8k tokens, 96 s/turn, 85 tok/s.
    write_trial(tmp_path, "thinker__a", turns=4, seconds=384, output_tokens=32_768, reward=0.0)
    # Compiling in the container, not a slow gateway: 12 s/turn, 6.7 tok/s.
    write_trial(tmp_path, "compiler__a", turns=25, seconds=300, output_tokens=2_000)
    # Degraded gateway: 612 s/turn, 0.7 tok/s, timed out.
    write_trial(tmp_path, "degraded__a", turns=11, seconds=6_732, output_tokens=5_000,
                reward=0.0, exception="AgentTimeoutError")
    # Dropped connection: the agent never got going.
    write_trial(tmp_path, "dropped__a", turns=None, seconds=1_320, output_tokens=0,
                reward=None, exception="APIConnectionError")
    return tmp_path


def by_id(trials):
    return {t.trial_id: t for t in trials}


def test_timing_is_read_from_result_json(job):
    t = by_id(load_trials(job))["normal__a"]
    assert t.seconds == pytest.approx(300)
    assert t.seconds_per_turn == pytest.approx(15)
    assert t.output_tokens_per_sec == pytest.approx(66.7, abs=0.1)


@pytest.mark.parametrize("trial, slow", [
    ("normal__a", False),
    ("thinker__a", False),   # long turns, but the model was producing tokens
    ("compiler__a", False),  # few tokens, but turns were quick
    ("degraded__a", True),   # slow turns and almost no tokens
])
def test_only_a_slow_gateway_is_flagged(job, trial, slow):
    assert by_id(load_trials(job))[trial].slow is slow


def test_missing_timing_is_never_flagged(tmp_path):
    write_trial(tmp_path, "old__a", seconds=None)
    t = load_trials(tmp_path)[0]
    assert t.seconds_per_turn is None
    assert t.slow is False


def test_connection_failures_count_as_zero_by_default(job):
    summary = summarize(load_trials(job))
    assert [t.trial_id for t in summary.infra_failures] == ["dropped__a"]
    dropped = next(t for t in summary.tasks if t.task == "dropped")
    assert dropped.reward == 0.0
    assert summary.tb_score == pytest.approx(2 / 5)


def test_connection_failures_can_be_left_out(job):
    summary = summarize(load_trials(job), drop_infra=True)
    assert "dropped" not in {t.task for t in summary.tasks}
    assert summary.tb_score == pytest.approx(2 / 4)
    assert summary.dropped_infra
    assert [t.trial_id for t in summary.infra_failures] == ["dropped__a"]


def test_report_warns_about_both_problems(job):
    text = format_table(summarize(load_trials(job)))
    assert "WARNING: 1 trial(s) slow at the gateway" in text
    assert "degraded__a" in text
    assert "thinker__a" not in text.split("WARNING")[1]
    assert "count as 0" in text and "dropped__a" in text


def test_healthy_run_says_so(tmp_path):
    write_trial(tmp_path, "normal__a")
    write_trial(tmp_path, "normal__b", seconds=360)
    text = format_table(summarize(load_trials(tmp_path)))
    assert "no slow trials, no connection failures" in text
    assert "WARNING" not in text
