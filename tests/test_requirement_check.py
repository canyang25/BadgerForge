"""Plan #30 and #31 through the real agent loop: the requirement checklist
before finishing, and the loop guard's failure stop turned into a reminder."""

import asyncio
from types import SimpleNamespace

from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.agent import BaselineAgent
from agent.loop_guard import CONSECUTIVE_FAILURE_ABORT_AT, LoopGuard
from agent.prompts import CHECKLIST_MESSAGE

DONE = "TASK_COMPLETE"


def command(n):
    return f"```bash\necho step {n}\n```"


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.last_truncated = False

    async def chat(self, messages, temperature=None):
        return self.replies.pop(0), {"prompt_tokens": 10, "completion_tokens": 5}


class Environment:
    def __init__(self, return_code=0):
        self.return_code = return_code

    async def exec(self, command, timeout_sec):
        return SimpleNamespace(stdout="out", stderr="", return_code=self.return_code)


def run(monkeypatch, tmp_path, replies, check=False, stop_on_failures=True, return_code=0):
    llm = ScriptedLLM(replies)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: llm)
    monkeypatch.setattr(agent_module, "REQUIREMENT_CHECK", check)
    monkeypatch.setattr(agent_module, "STOP_ON_FAILURES", stop_on_failures)
    context = AgentContext()
    asyncio.run(BaselineAgent(logs_dir=tmp_path).run("do it", Environment(return_code), context))
    return llm, context


def user_texts(context):
    return [m["content"] for m in context.metadata["messages"] if m["role"] == "user"]


def test_checklist_is_off_by_default(monkeypatch, tmp_path):
    _, context = run(monkeypatch, tmp_path, [DONE])
    assert context.metadata["finished"] is True
    assert CHECKLIST_MESSAGE not in user_texts(context)


def test_first_done_starts_the_checklist_and_the_second_ends(monkeypatch, tmp_path):
    _, context = run(monkeypatch, tmp_path, [command(1), DONE, command(2), DONE], check=True)
    assert user_texts(context).count(CHECKLIST_MESSAGE) == 1
    assert context.metadata["finished"] is True
    assert context.metadata["check_started_turn"] == 2
    assert context.metadata["check_turns"] == 2
    assert context.metadata["check_commands"] == 1


def test_checklist_names_the_kinds_of_requirement_that_were_missed():
    for phrase in ("speed thresholds", "data sources", "already passes"):
        assert phrase in CHECKLIST_MESSAGE


def test_failures_stop_the_task_by_default(monkeypatch, tmp_path):
    n = CONSECUTIVE_FAILURE_ABORT_AT
    llm, context = run(monkeypatch, tmp_path, [command(i) for i in range(n)], return_code=1)
    assert context.metadata["stopped_by_guard"] == "consecutive_failures"
    assert llm.replies == []


def test_with_the_stop_off_failures_only_remind(monkeypatch, tmp_path):
    n = CONSECUTIVE_FAILURE_ABORT_AT
    replies = [command(i) for i in range(n + 2)] + [DONE]
    _, context = run(monkeypatch, tmp_path, replies, stop_on_failures=False, return_code=1)
    assert context.metadata["stopped_by_guard"] is None
    assert context.metadata["finished"] is True
    reminders = [t for t in user_texts(context) if "in a row have exited non-zero" in t]
    assert len(reminders) == 1


def test_guard_reminds_every_eighth_failure_when_not_stopping():
    guard = LoopGuard(stop_on_failures=False)
    notes = [guard.after(f"cmd {i}", 1) for i in range(2 * CONSECUTIVE_FAILURE_ABORT_AT)]
    assert not any(v.stop for v in notes)
    assert [i for i, v in enumerate(notes) if v.note] == [7, 15]
