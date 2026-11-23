"""Thinking cap and overrun recovery, adapted from Badger Agents.

Our give-ups are replies cut off mid-thought several turns in a row (all 8-9
per run in the 11-20 and 11-21 full runs). Badger Agents cap most replies,
give the reply after a cut-off the full budget, hand the cut-off thinking back
as notes, and turn thinking off after two cut-offs in a row.
"""

import asyncio
from types import SimpleNamespace

import httpx
from openai import BadRequestError
from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.agent import BaselineAgent
from agent.llm import OVERRUN_NOTES_HEAD, OVERRUN_NOTES_TAIL, LLMClient, _overrun_notes
from agent.prompts import NUDGE_MESSAGE


def reply(content="", reasoning="", finish="stop"):
    message = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=100),
    )


CUT = dict(reasoning="first idea. " + "thinking " * 50 + "last idea.", finish="length")
OK = dict(content="```bash\nls\n```")
DONE = dict(content="TASK_COMPLETE")


class Scripted:
    """Plays back replies and records each request's keyword arguments."""

    def __init__(self, replies, reject_thinking_off=False):
        self.replies = [reply(**r) for r in replies]
        self.calls = []
        self.reject_thinking_off = reject_thinking_off

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.reject_thinking_off and "extra_body" in kwargs:
            raise BadRequestError(
                "unknown field",
                response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
                body=None,
            )
        return self.replies.pop(0)


def make_client(monkeypatch, replies, reject_thinking_off=False, **env):
    for name in ("AGENT_THINKING_CAP", "AGENT_OVERRUN_RECOVERY", "LLM_MAX_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_MODEL", "qwen3.8-27b")
    monkeypatch.setenv("LLM_API_KEY", "test")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    client = LLMClient()
    fake = Scripted(replies, reject_thinking_off)
    client._client.chat.completions = fake
    return client, fake


def chat_all(client, n):
    for _ in range(n):
        asyncio.run(client.chat([]))


def test_off_by_default(monkeypatch):
    client, fake = make_client(monkeypatch, [CUT, OK])
    chat_all(client, 2)
    assert [c["max_tokens"] for c in fake.calls] == [16384, 16384]
    assert not any("extra_body" in c for c in fake.calls)
    assert client.last_notes == ""


def test_cap_then_full_budget_right_after_a_cut_off(monkeypatch):
    client, fake = make_client(monkeypatch, [OK, CUT, OK, OK], AGENT_THINKING_CAP="8192")
    chat_all(client, 4)
    assert [c["max_tokens"] for c in fake.calls] == [8192, 8192, 16384, 8192]
    assert client.n_overruns == 1


def test_thinking_off_after_two_cut_offs_in_a_row(monkeypatch):
    client, fake = make_client(
        monkeypatch, [CUT, CUT, OK, OK], AGENT_THINKING_CAP="8192", AGENT_OVERRUN_RECOVERY="on"
    )
    chat_all(client, 4)
    off = [c.get("extra_body") for c in fake.calls]
    assert off == [None, None, {"chat_template_kwargs": {"enable_thinking": False}}, None]
    assert [c["max_tokens"] for c in fake.calls] == [8192, 16384, 16384, 8192]
    assert client.n_thinking_off_calls == 1


def test_a_gateway_that_rejects_the_switch_gets_a_normal_request(monkeypatch):
    client, fake = make_client(
        monkeypatch, [CUT, CUT, OK, CUT, CUT, OK], reject_thinking_off=True,
        AGENT_THINKING_CAP="8192", AGENT_OVERRUN_RECOVERY="on",
    )
    chat_all(client, 6)
    # One rejected attempt, then never again for this task.
    assert sum("extra_body" in c for c in fake.calls) == 1
    assert len(fake.calls) == 7
    assert client.thinking_off_rejected
    assert client.n_thinking_off_calls == 0


def test_notes_keep_the_start_and_the_end():
    thinking = "START " + "x" * 20_000 + " END"
    notes = _overrun_notes(SimpleNamespace(reasoning_content=thinking, content=""))
    assert notes.startswith("START")
    assert notes.endswith("END")
    assert "characters omitted" in notes
    assert len(notes) < OVERRUN_NOTES_HEAD + OVERRUN_NOTES_TAIL + 100


def test_notes_only_with_recovery_on(monkeypatch):
    client, _ = make_client(monkeypatch, [CUT, OK], AGENT_OVERRUN_RECOVERY="on")
    chat_all(client, 1)
    assert "first idea." in client.last_notes and "last idea." in client.last_notes
    chat_all(client, 1)
    assert client.last_notes == ""


class FakeEnvironment:
    async def exec(self, command, timeout_sec):
        return SimpleNamespace(stdout="ok", stderr="", return_code=0)


def run_agent(monkeypatch, tmp_path, replies, **env):
    client, _ = make_client(monkeypatch, replies, **env)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: client)
    context = AgentContext()
    asyncio.run(BaselineAgent(logs_dir=tmp_path).run("do the task", FakeEnvironment(), context))
    return context


def test_the_agent_hands_the_notes_back(monkeypatch, tmp_path):
    context = run_agent(
        monkeypatch, tmp_path, [CUT, OK, DONE], AGENT_THINKING_CAP="8192", AGENT_OVERRUN_RECOVERY="on"
    )
    messages = context.metadata["messages"]
    assert messages[2]["role"] == "assistant" and "notes below" in messages[2]["content"]
    assert messages[3]["content"].startswith(NUDGE_MESSAGE)
    assert "<notes>" in messages[3]["content"] and "last idea." in messages[3]["content"]
    assert context.metadata["overruns"] == 1


def test_without_recovery_the_agent_nudges_as_before(monkeypatch, tmp_path):
    context = run_agent(monkeypatch, tmp_path, [CUT, OK, DONE])
    messages = context.metadata["messages"]
    assert "last idea." in messages[2]["content"]
    assert messages[3]["content"] == NUDGE_MESSAGE
    assert context.metadata["overruns"] == 1
    assert context.metadata["thinking_off_calls"] == 0


def test_unfinished_thinking_is_never_acted_on(monkeypatch, tmp_path):
    # The cut-off thinking ends in what looks like a command and a finish.
    sneaky = dict(reasoning="plan... ```bash\nrm -rf /app\n``` TASK_COMPLETE", finish="length")
    context = run_agent(
        monkeypatch, tmp_path, [sneaky, OK, DONE], AGENT_THINKING_CAP="8192", AGENT_OVERRUN_RECOVERY="on"
    )
    messages = context.metadata["messages"]
    assert context.metadata["turns"] == 3
    assert "rm -rf" not in messages[2]["content"]
    assert "rm -rf" in messages[3]["content"]  # handed back as notes, not run
