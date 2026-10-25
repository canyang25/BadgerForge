"""The LangGraph loop makes the same decisions as the old for-loop.

No Docker and no model: a scripted client plays the replies back. The trace
is how we see which node spent the tokens.
"""

import asyncio
from types import SimpleNamespace

from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.agent import BaselineAgent
from agent.graph import build_graph
from agent.loop_guard import CONSECUTIVE_FAILURE_ABORT_AT, REPEAT_ABORT_AT

PREAMBLE = "Let's start by exploring the environment."
COMMAND = "```bash\nls -la\n```"
DONE = "TASK_COMPLETE"


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.temperatures = []
        self.last_truncated = False

    async def chat(self, messages, temperature=None):
        self.temperatures.append(temperature)
        text, self.last_truncated = self.replies.pop(0)
        return text, {"prompt_tokens": 10, "completion_tokens": 5}


class FakeEnvironment:
    def __init__(self, return_code=0):
        self.commands = []
        self.return_code = return_code

    async def exec(self, command, timeout_sec):
        self.commands.append(command)
        return SimpleNamespace(stdout="ok", stderr="", return_code=self.return_code)


def run(monkeypatch, tmp_path, replies, return_code=0):
    llm = ScriptedLLM(replies)
    env = FakeEnvironment(return_code=return_code)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: llm)
    context = AgentContext()
    agent = BaselineAgent(logs_dir=tmp_path)
    asyncio.run(agent.run("do the task", env, context))
    return llm, env, context


def nodes(context):
    return [row["node"] for row in context.metadata["node_trace"]]


def test_the_graph_is_the_four_loop_steps():
    names = set(build_graph().nodes) - {"__start__"}
    assert names == {"call_model", "nudge", "guard", "execute"}


def test_a_command_after_a_preamble_visits_each_node_and_counts_tokens(
    monkeypatch, tmp_path
):
    llm, env, context = run(
        monkeypatch, tmp_path, [(PREAMBLE, False), (COMMAND, False), (DONE, False)]
    )
    assert nodes(context) == [
        "call_model",
        "nudge",
        "call_model",
        "guard",
        "execute",
        "call_model",
    ]
    assert llm.temperatures == [None, 0.7, None]
    assert env.commands == ["ls -la"]
    assert context.metadata["finished"] is True
    assert context.metadata["commands_after_bump"] == 1
    spent = [row for row in context.metadata["node_trace"] if row["node"] == "call_model"]
    assert [row["prompt_tokens"] for row in spent] == [10, 10, 10]
    assert all(
        row["prompt_tokens"] == 0
        for row in context.metadata["node_trace"]
        if row["node"] != "call_model"
    )
    assert context.n_input_tokens == 30
    assert context.n_output_tokens == 15


def test_four_commandless_replies_stop_without_running_anything(monkeypatch, tmp_path):
    _, env, context = run(monkeypatch, tmp_path, [(PREAMBLE, False)] * 4)
    assert context.metadata["stop_reason"] == "no_action"
    assert "execute" not in nodes(context)
    assert env.commands == []
    assert nodes(context) == ["call_model", "nudge"] * 4


def test_a_repeated_command_is_refused_before_it_runs(monkeypatch, tmp_path):
    _, env, context = run(
        monkeypatch, tmp_path, [(COMMAND, False)] * (REPEAT_ABORT_AT + 1) + [(DONE, False)]
    )
    assert env.commands == ["ls -la"] * REPEAT_ABORT_AT
    assert context.metadata["finished"] is True
    # The refused attempt is a guard step with no execute after it.
    trace = nodes(context)
    followed_by = list(zip(trace, trace[1:] + ["end"]))
    refused = [node for node, nxt in followed_by if node == "guard" and nxt != "execute"]
    assert refused == ["guard"]


def test_eight_failures_in_a_row_stop_the_task(monkeypatch, tmp_path):
    replies = [(f"```bash\ncmd{i}\n```", False) for i in range(CONSECUTIVE_FAILURE_ABORT_AT)]
    llm, env, context = run(monkeypatch, tmp_path, replies, return_code=1)
    assert len(env.commands) == CONSECUTIVE_FAILURE_ABORT_AT
    assert len(llm.temperatures) == CONSECUTIVE_FAILURE_ABORT_AT
    assert context.metadata["stopped_by_guard"] == "consecutive_failures"
    assert context.metadata["finished"] is False


def test_the_turn_cap_stops_the_graph(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "MAX_TURNS", 2)
    llm, env, context = run(monkeypatch, tmp_path, [(COMMAND, False)] * 5)
    assert len(llm.temperatures) == 2
    assert len(env.commands) == 2
    assert context.metadata["turns"] == 2
    assert context.metadata["finished"] is False
