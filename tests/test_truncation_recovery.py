"""Recovery from truncated turns, exercised through the real agent loop.

A turn that runs out of output budget mid-thought and gives no command is
followed by one turn at lower reasoning effort. These tests drive
BaselineAgent.run with a scripted model and record the effort it asks for.
"""

import asyncio
from types import SimpleNamespace

from harbor.models.agent.context import AgentContext

import agent.agent as agent_mod
from agent.agent import BaselineAgent
from agent.llm import LLMClient


class ScriptedLLM:
    """Replays (text, truncated) replies and records the effort requested."""

    def __init__(self, script):
        self.script = list(script)
        self.efforts = []
        self.last_truncated = False

    async def chat(self, messages, reasoning_effort=None):
        self.efforts.append(reasoning_effort)
        text, truncated = self.script.pop(0)
        self.last_truncated = truncated
        return text, {"prompt_tokens": 10, "completion_tokens": 5}


class FakeEnvironment:
    async def exec(self, command, timeout_sec):
        return SimpleNamespace(stdout="ok", stderr="", return_code=0)


CUT = ("[your previous response was cut off — ...]\n...still thinking", True)
DONE = ("TASK_COMPLETE", False)


def cmd(i, truncated=False):
    return (f"```bash\necho step{i}\n```", truncated)


def run(monkeypatch, tmp_path, script, recovery="medium"):
    llm = ScriptedLLM(script)
    monkeypatch.setattr(agent_mod, "LLMClient", lambda model_name=None: llm)
    monkeypatch.setattr(agent_mod, "RECOVERY_EFFORT", recovery)
    context = AgentContext()
    agent = BaselineAgent(logs_dir=tmp_path)
    asyncio.run(agent.run("do the task", FakeEnvironment(), context))
    return llm, context.metadata


def test_one_recovery_turn_after_a_truncated_turn(monkeypatch, tmp_path):
    llm, meta = run(monkeypatch, tmp_path, [CUT, cmd(1), cmd(2), DONE])
    assert llm.efforts == [None, "medium", None, None]
    assert meta["recovery_turns"] == 1
    assert meta["recovery_actions"] == 1


def test_no_recovery_when_the_cut_off_turn_still_gave_a_command(monkeypatch, tmp_path):
    llm, meta = run(monkeypatch, tmp_path, [cmd(1, truncated=True), cmd(2), DONE])
    assert llm.efforts == [None, None, None]
    assert meta["recovery_turns"] == 0


def test_recovery_continues_while_the_model_keeps_getting_cut_off(monkeypatch, tmp_path):
    llm, meta = run(monkeypatch, tmp_path, [CUT, CUT, cmd(1), DONE])
    assert llm.efforts == [None, "medium", "medium", None]
    assert meta["recovery_turns"] == 2
    assert meta["recovery_actions"] == 1


def test_four_strikes_still_end_the_task(monkeypatch, tmp_path):
    llm, meta = run(monkeypatch, tmp_path, [CUT] * 4)
    assert llm.efforts == [None, "medium", "medium", "medium"]
    assert meta["stop_reason"] == "no_action"


def test_recovery_can_be_switched_off(monkeypatch, tmp_path):
    llm, meta = run(monkeypatch, tmp_path, [CUT, cmd(1), DONE], recovery="off")
    assert llm.efforts == [None, None, None]


def test_per_request_effort_overrides_the_default(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "qwen3.8-27b")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")
    client = LLMClient()
    assert client.extra_params() == {"reasoning_effort": "high"}
    assert client.extra_params("medium") == {"reasoning_effort": "medium"}
