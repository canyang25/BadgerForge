"""The optional check before finishing (plan #16), through the real agent loop.

With AGENT_VERIFY_BEFORE_DONE=1 the first TASK_COMPLETE doesn't end the task:
the model is asked to confirm every requirement and say TASK_COMPLETE again.
AGENT_VERIFY_EFFORT sets the reasoning effort for those turns only.
"""

import asyncio
from types import SimpleNamespace

from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.agent import BaselineAgent, parse_verify_effort
from agent.prompts import VERIFY_MESSAGE

COMMAND = "```bash\nls -la\n```"
DONE = "TASK_COMPLETE"


class ScriptedLLM:
    """Plays back replies and records each request's reasoning-effort override."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.efforts = []
        self.last_truncated = False

    async def chat(self, messages, temperature=None, reasoning_effort=None):
        self.efforts.append(reasoning_effort)
        return self.replies.pop(0), {"prompt_tokens": 10, "completion_tokens": 5}


class FakeEnvironment:
    async def exec(self, command, timeout_sec):
        return SimpleNamespace(stdout="ok", stderr="", return_code=0)


def run(monkeypatch, tmp_path, replies, verify, effort=None):
    llm = ScriptedLLM(replies)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: llm)
    monkeypatch.setattr(agent_module, "VERIFY_BEFORE_DONE", verify)
    monkeypatch.setattr(agent_module, "VERIFY_EFFORT", effort)
    context = AgentContext()
    asyncio.run(BaselineAgent(logs_dir=tmp_path).run("do it", FakeEnvironment(), context))
    return llm, context


def user_messages(context):
    return [m["content"] for m in context.metadata["messages"] if m["role"] == "user"]


def test_off_by_default_the_first_task_complete_ends_the_task(monkeypatch, tmp_path):
    llm, context = run(monkeypatch, tmp_path, [DONE], verify=False)
    assert len(llm.efforts) == 1
    assert context.metadata["finished"] is True
    assert VERIFY_MESSAGE not in user_messages(context)


def test_on_the_first_task_complete_starts_a_check(monkeypatch, tmp_path):
    llm, context = run(
        monkeypatch, tmp_path, [COMMAND, DONE, COMMAND, DONE], verify=True, effort=""
    )
    assert VERIFY_MESSAGE in user_messages(context)
    assert context.metadata["finished"] is True
    assert context.metadata["verify_started_turn"] == 2
    assert context.metadata["verify_turns"] == 2
    assert context.metadata["verify_commands"] == 1
    # The override applies to the check's turns only; "" leaves it to the server.
    assert llm.efforts == [None, None, "", ""]


def test_the_check_happens_once(monkeypatch, tmp_path):
    llm, context = run(monkeypatch, tmp_path, [DONE, DONE], verify=True)
    assert len(llm.efforts) == 2
    assert user_messages(context).count(VERIFY_MESSAGE) == 1
    assert context.metadata["finished"] is True


def test_effort_setting_parses():
    assert parse_verify_effort("") is None
    assert parse_verify_effort("server") == ""
    assert parse_verify_effort("high") == "high"


def test_llm_client_honours_the_per_request_override(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "qwen3.8-27b")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "medium")
    client = agent_module.LLMClient()
    assert client.extra_params() == {"reasoning_effort": "medium"}
    assert client.extra_params("") == {}
    assert client.extra_params("high") == {"reasoning_effort": "high"}
