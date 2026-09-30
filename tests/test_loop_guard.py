"""Loop guard: the stuck-detector that every baseline failure argues for."""

import pytest

from agent.loop_guard import (
    CONSECUTIVE_FAILURE_ABORT_AT,
    REPEAT_ABORT_AT,
    LoopGuard,
)
from agent.tools import parse_exit_code


def run(guard: LoopGuard, command: str, return_code: int = 0):
    """Simulate one turn: ask, execute, report back."""
    before = guard.before(command)
    if not before.run:
        return before
    return guard.after(command, return_code)


def test_first_run_of_a_command_is_silent():
    guard = LoopGuard()
    verdict = guard.before("ls /app")
    assert verdict.run and verdict.note is None


def test_second_identical_command_warns_but_still_runs():
    guard = LoopGuard()
    run(guard, "make")
    verdict = guard.before("make")
    assert verdict.run
    assert "already run" in verdict.note


def test_insisting_on_the_same_command_stops_running_it():
    guard = LoopGuard()
    for _ in range(REPEAT_ABORT_AT):
        run(guard, "make", return_code=1)
    verdict = guard.before("make")
    assert verdict.run is False
    assert "something different" in verdict.note.lower()


def test_different_commands_never_trip_the_repeat_check():
    guard = LoopGuard()
    for i in range(10):
        assert guard.before(f"cat file{i}").run
        guard.after(f"cat file{i}", 0)


def test_a_run_of_failures_stops_the_task():
    guard = LoopGuard()
    verdicts = [run(guard, f"cmd{i}", return_code=1) for i in range(CONSECUTIVE_FAILURE_ABORT_AT)]
    assert not any(v.stop for v in verdicts[:-1])
    assert verdicts[-1].stop
    assert "failed" in verdicts[-1].note


def test_one_success_resets_the_failure_run():
    guard = LoopGuard()
    for i in range(CONSECUTIVE_FAILURE_ABORT_AT - 1):
        run(guard, f"bad{i}", return_code=1)
    run(guard, "good", return_code=0)
    assert guard.consecutive_failures == 0
    assert not run(guard, "bad-again", return_code=1).stop


@pytest.mark.parametrize(
    "observation,expected",
    [
        ("exit code: 0\nstdout:\nhi", 0),
        ("exit code: 127\nstderr:\nnot found", 127),
        ("[command did not complete: timeout]", 1),
        ("exit code: not-a-number", 1),
    ],
)
def test_exit_code_parsing(observation, expected):
    assert parse_exit_code(observation) == expected
