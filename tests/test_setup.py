"""setup() waits for apt/dpkg left running by the image, and never fails a task."""

import asyncio

from agent.agent import APT_WAIT_COMMAND, APT_WAIT_SEC, BaselineAgent


class RecordingEnvironment:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def exec(self, command, timeout_sec):
        self.calls.append((command, timeout_sec))
        if self.error:
            raise self.error


def test_setup_waits_for_apt_with_a_bounded_timeout(tmp_path):
    env = RecordingEnvironment()
    asyncio.run(BaselineAgent(logs_dir=tmp_path).setup(env))
    [(command, timeout)] = env.calls
    assert command == APT_WAIT_COMMAND
    assert timeout > APT_WAIT_SEC


def test_setup_carries_on_if_the_wait_fails(tmp_path):
    env = RecordingEnvironment(error=RuntimeError("exec failed"))
    asyncio.run(BaselineAgent(logs_dir=tmp_path).setup(env))
    assert len(env.calls) == 1


def test_the_wait_only_reads_proc_and_uses_plain_sh():
    assert "/proc/" in APT_WAIT_COMMAND
    for tool in ("pgrep", "fuser", "lsof", "rm "):
        assert tool not in APT_WAIT_COMMAND
