"""Dropping to a lower reasoning effort when a task runs long.

On the 2026-11-19 full run the server's default effort halved wrong answers
against medium but doubled timeouts; the timed-out trials thought 4-5k tokens
per turn. The switch keeps the default effort early and lowers it once the
task has run a while and recent replies are long.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.agent import BaselineAgent
from agent.effort_switch import EffortSwitch

REPO = Path(__file__).resolve().parent.parent
COMMAND = "```bash\nls -la\n```"
DONE = "TASK_COMPLETE"


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_never_switches_when_off():
    clock = FakeClock()
    sw = EffortSwitch("", after_sec=0, min_tokens=0, clock=clock)
    clock.now = 1000
    assert not any(sw.record(10_000, turn) for turn in range(1, 6))
    assert sw.switched_turn is None


def test_waits_for_the_time_and_for_long_replies():
    clock = FakeClock()
    sw = EffortSwitch("medium", after_sec=360, min_tokens=3000, clock=clock)
    # Long replies, but too early.
    clock.now = 100
    assert not any(sw.record(5000, turn) for turn in (1, 2, 3))
    assert sw.switched_turn is None


def test_switches_once_the_last_three_replies_average_long_enough():
    clock = FakeClock()
    sw = EffortSwitch("medium", after_sec=360, min_tokens=3000, clock=clock)
    clock.now = 100
    assert not any(sw.record(500, turn) for turn in (1, 2, 3))
    clock.now = 400
    assert not sw.record(4000, 4)  # last three: 500, 500, 4000
    assert not sw.record(4000, 5)  # 500, 4000, 4000: under 3000 on average
    assert sw.record(4000, 6)      # 4000, 4000, 4000
    assert sw.switched_turn == 6
    assert sw.switched_elapsed == 400.0


def test_switches_only_once():
    clock = FakeClock()
    sw = EffortSwitch("medium", after_sec=0, min_tokens=0, clock=clock)
    assert not sw.record(1, 1)
    assert not sw.record(1, 2)
    assert sw.record(1, 3)
    assert not sw.record(1, 4)
    assert sw.switched_turn == 3


class ScriptedLLM:
    """Plays back replies with given completion tokens; records the effort of each request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.efforts = []
        self.last_truncated = False
        self.reasoning_effort = None

    async def chat(self, messages, temperature=None):
        self.efforts.append(self.reasoning_effort)
        text, tokens = self.replies.pop(0)
        return text, {"prompt_tokens": 10, "completion_tokens": tokens}


class FakeEnvironment:
    async def exec(self, command, timeout_sec):
        return SimpleNamespace(stdout="ok", stderr="", return_code=0)


def run(monkeypatch, tmp_path, replies, target):
    llm = ScriptedLLM(replies)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: llm)
    monkeypatch.setattr(agent_module, "EFFORT_SWITCH", target)
    monkeypatch.setattr(agent_module, "EFFORT_SWITCH_AFTER_SEC", 0.0)
    monkeypatch.setattr(agent_module, "EFFORT_SWITCH_MIN_TOKENS", 3000.0)
    context = AgentContext()
    asyncio.run(BaselineAgent(logs_dir=tmp_path).run("do the task", FakeEnvironment(), context))
    return llm, context


def test_the_agent_lowers_effort_after_three_long_replies(monkeypatch, tmp_path):
    replies = [(f"```bash\nls {i}\n```", 4000) for i in range(3)] + [(COMMAND, 500), (DONE, 100)]
    llm, context = run(monkeypatch, tmp_path, replies, "medium")
    assert llm.efforts == [None, None, None, "medium", "medium"]
    assert context.metadata["effort_switch_turn"] == 3


def test_switch_off_leaves_effort_alone(monkeypatch, tmp_path):
    replies = [(f"```bash\nls {i}\n```", 4000) for i in range(3)] + [(DONE, 100)]
    llm, context = run(monkeypatch, tmp_path, replies, "")
    assert llm.efforts == [None, None, None, None]
    assert context.metadata["effort_switch_turn"] is None


def test_clean_environment_starts_at_server_default_then_medium():
    """With no effort settings at all, the first request leaves the effort to
    the server and a switch sends medium: the submission's defaults live in
    code, not only in .env.op."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("LLM_REASONING_EFFORT", "AGENT_EFFORT_SWITCH")}
    code = (
        "import agent.agent as a\n"
        "from agent.llm import LLMClient\n"
        "c = LLMClient('qwen3.8-27b')\n"
        "print(c.extra_params(), a.EFFORT_SWITCH)\n"
        "c.reasoning_effort = a.EFFORT_SWITCH\n"
        "print(c.extra_params())\n"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=REPO,
                         capture_output=True, text=True, check=True).stdout
    assert out.splitlines() == ["{} medium", "{'reasoning_effort': 'medium'}"]
