"""The environment survey that runs before the model's first turn."""

import asyncio
from types import SimpleNamespace

import agent.probe as probe


class FakeEnvironment:
    def __init__(self, stdout="", error=None):
        self.stdout = stdout
        self.error = error
        self.commands = []

    async def exec(self, command, timeout_sec):
        self.commands.append(command)
        if self.error:
            raise self.error
        return SimpleNamespace(stdout=self.stdout, stderr="", return_code=0)


def test_survey_is_framed_for_the_model():
    env = FakeEnvironment("working dir: /app\nnetwork: reachable\n")
    report = asyncio.run(probe.survey(env))
    assert report.startswith("Environment survey")
    assert "network: reachable" in report
    assert len(env.commands) == 1


def test_long_output_is_capped():
    env = FakeEnvironment("x" * 10_000)
    report = asyncio.run(probe.survey(env))
    assert "survey truncated" in report
    assert len(report) < probe.PROBE_MAX_CHARS + 200


def test_a_failing_probe_never_breaks_the_task():
    env = FakeEnvironment(error=TimeoutError("container slow"))
    assert asyncio.run(probe.survey(env)) is None


def test_empty_output_gives_no_report():
    assert asyncio.run(probe.survey(FakeEnvironment(""))) is None


def test_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(probe, "PROBE_ENABLED", False)
    env = FakeEnvironment("anything")
    assert asyncio.run(probe.survey(env)) is None
    assert env.commands == []


def test_probe_mentions_no_specific_task():
    # Guard against drifting into task-specific hints, which the rules forbid.
    for word in ("chess", "font", "stockfish", "regex", "sqlite", "nginx"):
        assert word not in probe.PROBE_COMMAND.lower()
