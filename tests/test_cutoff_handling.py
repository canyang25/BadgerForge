"""What a reply cut off at max_tokens leaves behind (plan #25), through the real loop.

"tail" is what we've always run; "concise" and "drop" follow mini-swe-agent.
Cut-off turns are counted in metadata, since "drop" leaves no trace of them
in the transcript.
"""

import asyncio
from types import SimpleNamespace

from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.agent import BaselineAgent
from agent.prompts import ACT_NUDGE_MESSAGE, CUTOFF_MESSAGE, NUDGE_MESSAGE

CUT = "[your previous response was cut off ...] ...still thinking about"
PREAMBLE = "Let's start by exploring the environment."
COMMAND = "```bash\nls -la\n```"
DONE = "TASK_COMPLETE"


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.last_truncated = False

    async def chat(self, messages, temperature=None):
        text, self.last_truncated = self.replies.pop(0)
        return text, {"prompt_tokens": 10, "completion_tokens": 5}


class FakeEnvironment:
    async def exec(self, command, timeout_sec):
        return SimpleNamespace(stdout="ok", stderr="", return_code=0)


def run(monkeypatch, tmp_path, replies, mode):
    llm = ScriptedLLM(replies)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: llm)
    monkeypatch.setattr(agent_module, "CUTOFF_HANDLING", mode)
    context = AgentContext()
    asyncio.run(BaselineAgent(logs_dir=tmp_path).run("do it", FakeEnvironment(), context))
    return context


def texts(context, role):
    return [m["content"] for m in context.metadata["messages"] if m["role"] == role]


ONE_CUT = [(CUT, True), (COMMAND, False), (DONE, False)]


def test_tail_keeps_the_cut_off_text_and_the_generic_nudge(monkeypatch, tmp_path):
    context = run(monkeypatch, tmp_path, ONE_CUT, "tail")
    assert CUT in texts(context, "assistant")
    assert NUDGE_MESSAGE in texts(context, "user")
    assert CUTOFF_MESSAGE not in texts(context, "user")
    assert context.metadata["cut_off_turns"] == 1


def test_concise_keeps_the_text_and_asks_for_brevity(monkeypatch, tmp_path):
    context = run(monkeypatch, tmp_path, ONE_CUT, "concise")
    assert CUT in texts(context, "assistant")
    assert CUTOFF_MESSAGE in texts(context, "user")
    assert NUDGE_MESSAGE not in texts(context, "user")


def test_drop_leaves_the_cut_off_reply_out_of_the_history(monkeypatch, tmp_path):
    context = run(monkeypatch, tmp_path, ONE_CUT, "drop")
    assert CUT not in texts(context, "assistant")
    assert texts(context, "assistant") == [COMMAND, DONE]
    assert CUTOFF_MESSAGE in texts(context, "user")
    assert context.metadata["cut_off_turns"] == 1
    assert context.metadata["finished"] is True


def test_drop_doesnt_touch_replies_that_werent_cut_off(monkeypatch, tmp_path):
    context = run(
        monkeypatch, tmp_path, [(PREAMBLE, False), (COMMAND, False), (DONE, False)], "drop"
    )
    assert PREAMBLE in texts(context, "assistant")
    assert ACT_NUDGE_MESSAGE in texts(context, "user")
    assert context.metadata["cut_off_turns"] == 0


def test_the_give_up_rule_is_unchanged_under_drop(monkeypatch, tmp_path):
    context = run(monkeypatch, tmp_path, [(CUT, True)] * 4, "drop")
    assert context.metadata["stop_reason"] == "no_action"
    assert context.metadata["cut_off_turns"] == 4
