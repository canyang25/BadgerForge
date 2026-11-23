"""Submit check and time awareness, adapted from Badger Agents.

Wrong answers are our largest loss (13-16 per full run); their submit check
answers the first finish once with a checklist. Timeouts are next; their time
awareness shows the minutes used after each command and nudges once at 10.
"""

import asyncio
from types import SimpleNamespace

from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.agent import BaselineAgent
from agent.prompts import SUBMIT_CHECK_MESSAGE, SYSTEM_PROMPT, TIME_NUDGE_MESSAGE, TIME_RULE

COMMAND = "```bash\nls\n```"
DONE = "TASK_COMPLETE"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeLLM:
    """Plays back replies; each reply takes `step` seconds on the fake clock."""

    def __init__(self, replies, clock, step=0.0):
        self.replies = list(replies)
        self.clock = clock
        self.step = step
        self.last_truncated = False
        self.last_notes = ""
        self.n_overruns = 0
        self.n_thinking_off_calls = 0
        self.thinking_off_rejected = False
        self.reasoning_effort = None

    async def chat(self, messages, temperature=None):
        self.clock.now += self.step
        return self.replies.pop(0), {"prompt_tokens": 10, "completion_tokens": 10}


class FakeEnvironment:
    async def exec(self, command, timeout_sec):
        return SimpleNamespace(stdout="ok", stderr="", return_code=0)


def run(monkeypatch, tmp_path, replies, submit_check=False, time_awareness=False, step=0.0):
    clock = Clock()
    llm = FakeLLM(replies, clock, step)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: llm)
    monkeypatch.setattr(agent_module, "SUBMIT_CHECK", submit_check)
    monkeypatch.setattr(agent_module, "TIME_AWARENESS", time_awareness)
    monkeypatch.setattr(agent_module, "_clock", clock)
    context = AgentContext()
    asyncio.run(BaselineAgent(logs_dir=tmp_path).run("do the task", FakeEnvironment(), context))
    return context


def test_first_finish_is_answered_with_the_checklist(monkeypatch, tmp_path):
    context = run(monkeypatch, tmp_path, [DONE, COMMAND, DONE], submit_check=True)
    messages = context.metadata["messages"]
    assert messages[3]["content"] == SUBMIT_CHECK_MESSAGE  # time awareness off: no clock
    assert context.metadata["finished"] is True
    assert context.metadata["turns"] == 3
    assert context.metadata["submit_checked_turn"] == 1


def test_without_the_check_the_first_finish_ends_the_task(monkeypatch, tmp_path):
    context = run(monkeypatch, tmp_path, [DONE])
    assert context.metadata["finished"] is True
    assert context.metadata["turns"] == 1
    assert context.metadata["submit_checked_turn"] is None


def test_minutes_used_after_each_command_and_one_nudge_at_ten(monkeypatch, tmp_path):
    context = run(
        monkeypatch, tmp_path, [COMMAND, COMMAND, COMMAND, DONE], time_awareness=True, step=400.0
    )
    messages = context.metadata["messages"]
    assert messages[0]["content"] == f"{SYSTEM_PROMPT}\n\n{TIME_RULE}"
    observations = [m["content"] for m in messages if m["role"] == "user"][1:]
    assert "[time used: 6 min" in observations[0] and TIME_NUDGE_MESSAGE not in observations[0]
    assert "[time used: 13 min" in observations[1] and TIME_NUDGE_MESSAGE in observations[1]
    assert "[time used: 20 min" in observations[2] and TIME_NUDGE_MESSAGE not in observations[2]
    assert context.metadata["time_nudged_at_sec"] == 800.0


def test_time_awareness_off_leaves_prompts_alone(monkeypatch, tmp_path):
    context = run(monkeypatch, tmp_path, [COMMAND, DONE], step=700.0)
    messages = context.metadata["messages"]
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert "time used" not in messages[3]["content"]
    assert context.metadata["time_nudged_at_sec"] is None


def test_no_checklist_on_the_last_turn(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "MAX_TURNS", 2)
    context = run(monkeypatch, tmp_path, [COMMAND, DONE], submit_check=True)
    assert context.metadata["finished"] is True
    assert context.metadata["submit_checked_turn"] is None


def test_the_checklist_carries_the_clock(monkeypatch, tmp_path):
    context = run(monkeypatch, tmp_path, [DONE, DONE], submit_check=True, time_awareness=True, step=700.0)
    checklist = context.metadata["messages"][3]["content"]
    assert checklist.startswith(SUBMIT_CHECK_MESSAGE)
    assert "[time used: 11 min" in checklist and TIME_NUDGE_MESSAGE in checklist
