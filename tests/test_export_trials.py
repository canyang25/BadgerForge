"""Per-trial export used to pick a dev slice from a broad run."""

import csv
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "export_trials", Path(__file__).parent.parent / "scripts" / "export_trials.py"
)
export_trials = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export_trials)

FIXTURE = Path(__file__).parent / "fixtures" / "job"


@pytest.mark.parametrize("reward, exception, stop, expected", [
    (1.0, None, None, "pass"),
    (0.0, None, None, "wrong_answer"),
    (0.0, "AgentTimeoutError", None, "timeout"),
    (1.0, "AgentTimeoutError", None, "pass"),  # passed even though it hit the timeout
    (0.0, None, "no_action", "gave_up"),
    (None, "APIConnectionError", None, "gateway_failure"),
])
def test_outcome(reward, exception, stop, expected):
    assert export_trials.outcome(reward, exception, stop) == expected


def test_exports_every_trial(tmp_path, monkeypatch):
    out = tmp_path / "trials.csv"
    monkeypatch.setattr("sys.argv", ["export_trials.py", str(FIXTURE), "--out", str(out)])
    assert export_trials.main() == 0
    rows = list(csv.DictReader(out.open()))
    assert len(rows) == 3
    assert {r["task"] for r in rows} == {"regex-log", "qemu-startup"}
    assert {r["outcome"] for r in rows} == {"pass", "wrong_answer"}
