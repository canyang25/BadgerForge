"""The LangGraph loop makes the same decisions as the old for-loop.

No Docker and no model: a scripted client plays the replies back. The trace
is how we see which node spent the tokens.
"""

import asyncio
from types import SimpleNamespace

import pytest
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
    def __init__(self, return_code=0, stdout="ok", stderr=""):
        self.commands = []
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr

    async def exec(self, command, timeout_sec):
        self.commands.append(command)
        return SimpleNamespace(
            stdout=self.stdout, stderr=self.stderr, return_code=self.return_code
        )


def run(monkeypatch, tmp_path, replies, return_code=0, stdout="ok", stderr=""):
    llm = ScriptedLLM(replies)
    env = FakeEnvironment(return_code=return_code, stdout=stdout, stderr=stderr)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: llm)
    context = AgentContext()
    agent = BaselineAgent(logs_dir=tmp_path)
    asyncio.run(agent.run("do the task", env, context))
    return llm, env, context


def nodes(context):
    return [row["node"] for row in context.metadata["node_trace"]]


def test_the_graph_is_the_loop_plus_the_optional_nodes():
    names = set(build_graph().nodes) - {"__start__"}
    assert names == {
        "call_model",
        "nudge",
        "guard",
        "execute",
        "shape",
        "progress",
        "deliverable",
    }


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


def user_text(context):
    return "\n".join(
        message["content"] for message in context.metadata["messages"] if message["role"] == "user"
    )


def test_progress_and_shape_stay_off_unless_asked(monkeypatch, tmp_path):
    replies = [(f"```bash\necho {i}\n```", False) for i in range(10)] + [(DONE, False)]
    _, _, context = run(monkeypatch, tmp_path, replies, stdout="y" * 20_000)
    assert "progress" not in nodes(context)
    assert "shape" not in nodes(context)
    assert "deliverable" not in nodes(context)
    assert "Progress check" not in user_text(context)
    assert "That output was cut" not in user_text(context)
    assert "Early deliverable checkpoint." not in user_text(context)


def test_a_progress_check_lands_on_turn_10(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "PROGRESS_CHECK", True)
    replies = [(f"```bash\necho {i}\n```", False) for i in range(10)] + [(DONE, False)]
    _, _, context = run(monkeypatch, tmp_path, replies)
    fired = [row for row in context.metadata["node_trace"] if row["node"] == "progress"]
    assert [row["turn"] for row in fired] == [10]
    assert fired[0]["reasons"] == ["periodic"]
    assert fired[0]["progress_every"] == 10
    assert fired[0]["identical_failures"] == 0
    assert "Progress check" in user_text(context)
    assert context.metadata["finished"] is True


@pytest.mark.parametrize("interval", [10, 0])
def test_three_identical_failures_ask_for_a_new_approach(monkeypatch, tmp_path, interval):
    monkeypatch.setattr(agent_module, "PROGRESS_CHECK", True)
    monkeypatch.setattr(agent_module, "PROGRESS_EVERY", interval)
    _, _, context = run(
        monkeypatch, tmp_path, [(COMMAND, False)] * 3 + [(DONE, False)], return_code=1
    )
    assert nodes(context).count("progress") == 1
    assert "switch approach" in user_text(context)
    fired = [row for row in context.metadata["node_trace"] if row["node"] == "progress"]
    assert fired[0]["reasons"] == ["identical_failures"]
    assert fired[0]["identical_failures"] == 3


def test_one_progress_event_records_both_triggers(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "PROGRESS_CHECK", True)
    monkeypatch.setattr(agent_module, "PROGRESS_EVERY", 3)
    _, _, context = run(
        monkeypatch, tmp_path, [(COMMAND, False)] * 3 + [(DONE, False)], return_code=1
    )
    fired = [row for row in context.metadata["node_trace"] if row["node"] == "progress"]
    assert len(fired) == 1
    assert fired[0]["reasons"] == ["periodic", "identical_failures"]
    assert user_text(context).count("Progress check.") == 1


def test_two_failures_or_three_different_ones_do_not_ask(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "PROGRESS_CHECK", True)
    _, _, short = run(
        monkeypatch, tmp_path, [(COMMAND, False)] * 2 + [(DONE, False)], return_code=1
    )
    different = [(f"```bash\ncmd{i}\n```", False) for i in range(3)] + [(DONE, False)]
    _, _, varied = run(monkeypatch, tmp_path, different, return_code=1)
    assert "progress" not in nodes(short)
    assert "progress" not in nodes(varied)


def test_a_cut_output_keeps_the_text_and_says_to_narrow_it(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "OBSERVATION_SHAPE", True)
    _, _, context = run(
        monkeypatch, tmp_path, [(COMMAND, False), (DONE, False)], stdout="y" * 20_000
    )
    text = user_text(context)
    assert "shape" in nodes(context)
    assert "characters omitted" in text
    assert "That output was cut" in text


def test_a_binary_dump_is_replaced_with_a_short_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "OBSERVATION_SHAPE", True)
    _, _, context = run(
        monkeypatch, tmp_path, [(COMMAND, False), (DONE, False)], stdout="\x00" * 40
    )
    text = user_text(context)
    assert "\x00" not in text
    assert "binary" in text
    assert "raw dump" in text


def test_a_numeric_table_is_replaced_with_its_shape(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "OBSERVATION_SHAPE", True)
    row = "1.5 2.5 3.5 4.5 5.5"
    _, _, context = run(
        monkeypatch,
        tmp_path,
        [(COMMAND, False), (DONE, False)],
        stdout="\n".join([row] * 12),
    )
    text = user_text(context)
    assert "numeric table" in text
    assert text.count(row) == 2


def test_the_turn_cap_stops_the_graph(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "MAX_TURNS", 2)
    llm, env, context = run(monkeypatch, tmp_path, [(COMMAND, False)] * 5)
    assert len(llm.temperatures) == 2
    assert len(env.commands) == 2
    assert context.metadata["turns"] == 2
    assert context.metadata["finished"] is False


def test_early_deliverable_fires_once_without_an_extra_model_call(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "EARLY_DELIVERABLE", True)
    monkeypatch.setattr(agent_module, "DELIVERABLE_TURN", 3)
    replies = [(f"```bash\necho {i}\n```", False) for i in range(7)] + [(DONE, False)]
    llm, env, context = run(monkeypatch, tmp_path, replies)
    events = [row for row in context.metadata["node_trace"] if row["node"] == "deliverable"]
    assert len(events) == 1
    assert events[0]["turn"] == events[0]["scheduled_turn"] == 3
    assert user_text(context).count("Early deliverable checkpoint.") == 1
    assert len(llm.temperatures) == 8
    assert len(env.commands) == 7
    assert context.metadata["finished"] is True


def test_early_completion_is_not_intercepted(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "EARLY_DELIVERABLE", True)
    _, _, context = run(monkeypatch, tmp_path, [(COMMAND, False), (DONE, False)])
    assert "deliverable" not in nodes(context)
    assert context.metadata["finished"] is True


def test_early_deliverable_never_runs_after_the_turn_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "EARLY_DELIVERABLE", True)
    monkeypatch.setattr(agent_module, "DELIVERABLE_TURN", 2)
    monkeypatch.setattr(agent_module, "MAX_TURNS", 2)
    llm, env, context = run(monkeypatch, tmp_path, [(COMMAND, False)] * 2)
    assert "deliverable" not in nodes(context)
    assert len(llm.temperatures) == len(env.commands) == 2


def test_deliverable_and_progress_can_fire_together_without_looping(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "EARLY_DELIVERABLE", True)
    monkeypatch.setattr(agent_module, "DELIVERABLE_TURN", 3)
    monkeypatch.setattr(agent_module, "PROGRESS_CHECK", True)
    monkeypatch.setattr(agent_module, "PROGRESS_EVERY", 3)
    llm, _, context = run(monkeypatch, tmp_path, [(COMMAND, False)] * 3 + [(DONE, False)])
    optional = [node for node in nodes(context) if node in ("deliverable", "progress")]
    assert optional == ["deliverable", "progress"]
    assert len(llm.temperatures) == 4


def test_refused_commands_do_not_trigger_early_deliverable(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "EARLY_DELIVERABLE", True)
    monkeypatch.setattr(agent_module, "DELIVERABLE_TURN", 4)
    _, env, context = run(monkeypatch, tmp_path, [(COMMAND, False)] * 4 + [(DONE, False)])
    assert len(env.commands) == 3
    assert "deliverable" not in nodes(context)


def test_commandless_turns_do_not_trigger_early_deliverable(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "EARLY_DELIVERABLE", True)
    monkeypatch.setattr(agent_module, "DELIVERABLE_TURN", 1)
    _, _, context = run(monkeypatch, tmp_path, [(PREAMBLE, False)] * 4)
    assert "deliverable" not in nodes(context)
    assert context.metadata["stop_reason"] == "no_action"


@pytest.mark.parametrize("threshold", [0, -1])
def test_nonpositive_deliverable_turn_disables_the_checkpoint(monkeypatch, tmp_path, threshold):
    monkeypatch.setattr(agent_module, "EARLY_DELIVERABLE", True)
    monkeypatch.setattr(agent_module, "DELIVERABLE_TURN", threshold)
    _, _, context = run(monkeypatch, tmp_path, [(COMMAND, False)] * 3 + [(DONE, False)])
    assert "deliverable" not in nodes(context)


def test_shaping_then_deliverable_then_progress_share_the_next_turn(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "EARLY_DELIVERABLE", True)
    monkeypatch.setattr(agent_module, "DELIVERABLE_TURN", 1)
    monkeypatch.setattr(agent_module, "PROGRESS_CHECK", True)
    monkeypatch.setattr(agent_module, "PROGRESS_EVERY", 1)
    monkeypatch.setattr(agent_module, "OBSERVATION_SHAPE", True)
    llm, _, context = run(
        monkeypatch, tmp_path, [(COMMAND, False), (DONE, False)], stdout="\x00" * 40
    )
    optional = [node for node in nodes(context) if node in ("shape", "deliverable", "progress")]
    assert optional == ["shape", "deliverable", "progress"]
    assert len(llm.temperatures) == 2
    assert context.n_input_tokens == 20
