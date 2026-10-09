"""Replies that end without a command, driven through the real agent loop.

In the 2026-10-07 full run four tasks quit within 3 seconds: the model
announced a step four times ("Let's start by exploring the environment.",
"Let me explore the environment first.", ...) without ever running one, and
the agent gave up. A reply that was cut off
mid-thought is a different failure and keeps the old nudge.
"""

import asyncio
from types import SimpleNamespace

import pytest
from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.agent import NO_COMMAND_TEMPERATURE, BaselineAgent
from agent.prompts import ACT_NUDGE_MESSAGE, NUDGE_MESSAGE

PREAMBLE = "Let's start by exploring the environment."
COMMAND = "```bash\nls -la\n```"
DONE = "TASK_COMPLETE"


class ScriptedLLM:
    """Plays back (text, truncated) replies and records each request's temperature."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.temperatures = []
        self.last_truncated = False

    async def chat(self, messages, temperature=None):
        self.temperatures.append(temperature)
        text, self.last_truncated = self.replies.pop(0)
        return text, {"prompt_tokens": 10, "completion_tokens": 5}


class FakeEnvironment:
    async def exec(self, command, timeout_sec):
        return SimpleNamespace(stdout="ok", stderr="", return_code=0)


def run(monkeypatch, tmp_path, replies):
    llm = ScriptedLLM(replies)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: llm)
    context = AgentContext()
    agent = BaselineAgent(logs_dir=tmp_path)
    asyncio.run(agent.run("do the task", FakeEnvironment(), context))
    return llm, context


def user_messages(context):
    return [m["content"] for m in context.metadata["messages"] if m["role"] == "user"]


def test_a_reply_without_a_command_gets_the_act_nudge_and_one_hotter_request(
    monkeypatch, tmp_path
):
    llm, context = run(
        monkeypatch, tmp_path, [(PREAMBLE, False), (COMMAND, False), (DONE, False)]
    )
    assert llm.temperatures == [None, NO_COMMAND_TEMPERATURE, None]
    assert ACT_NUDGE_MESSAGE in user_messages(context)
    assert context.metadata["no_command_replies"] == 1
    assert context.metadata["commands_after_bump"] == 1
    assert context.metadata["finished"] is True


def test_a_cut_off_reply_keeps_the_old_nudge_and_temperature(monkeypatch, tmp_path):
    llm, context = run(
        monkeypatch, tmp_path, [("...thinking", True), (COMMAND, False), (DONE, False)]
    )
    assert llm.temperatures == [None, None, None]
    assert NUDGE_MESSAGE in user_messages(context)
    assert ACT_NUDGE_MESSAGE not in user_messages(context)
    assert context.metadata["no_command_replies"] == 0


def test_the_give_up_rule_is_unchanged(monkeypatch, tmp_path):
    llm, context = run(monkeypatch, tmp_path, [(PREAMBLE, False)] * 4)
    assert context.metadata["stop_reason"] == "no_action"
    assert context.metadata["turns"] == 4
    assert context.metadata["no_command_replies"] == 4
    assert context.metadata["commands_after_bump"] == 0


@pytest.mark.parametrize("temperature", [None, 0.7])
def test_llm_client_sends_the_override_only_when_given(monkeypatch, temperature):
    monkeypatch.setenv("LLM_MODEL", "qwen3.8-27b")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")
    client = agent_module.LLMClient()
    sent = {}

    class Completions:
        async def create(self, **kwargs):
            sent.update(kwargs)
            choice = SimpleNamespace(
                message=SimpleNamespace(content=COMMAND), finish_reason="stop"
            )
            return SimpleNamespace(choices=[choice], usage=None)

    client._client.chat.completions = Completions()
    asyncio.run(client.chat([], temperature=temperature))
    assert sent["temperature"] == (0.2 if temperature is None else temperature)
    assert client.last_truncated is False
