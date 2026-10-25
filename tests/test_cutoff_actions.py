import asyncio
from types import SimpleNamespace

import pytest
from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.llm import LLMClient, REASONING_TAIL_CHARS, _tail

COMMAND = "cat > /app/solution.py <<'PY'\n" + "# padding\n" * 240 + "print('done')\nPY"
BLOCK = f"```bash\n{COMMAND}\n```"
DRAFT = ("thinking " * 400) + "\n```bash\necho draft\n```"


@pytest.mark.parametrize("content, reasoning, finish_reason, executes", [
    (BLOCK, None, "length", True),
    (BLOCK[:-3], None, "length", False),
    (BLOCK, None, "stop", True),
    (None, DRAFT, "length", False),
    (None, "```bash\necho draft\n```", "stop", False),
])
def test_full_content_runs_and_reasoning_does_not(
    monkeypatch, tmp_path, content, reasoning, finish_reason, executes
):
    replies = iter([(content, reasoning, finish_reason), ("TASK_COMPLETE", None, "stop")])
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test")
    client = LLMClient()

    async def request(*args):
        reply_content, reply_reasoning, finish = next(replies)
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=reply_content, reasoning_content=reply_reasoning),
                finish_reason=finish,
            )],
            usage=None,
        )

    commands = []

    class Environment:
        async def exec(self, command, timeout_sec):
            commands.append(command)
            return SimpleNamespace(stdout="ok", stderr="", return_code=0)

    monkeypatch.setattr(client, "_request_with_retries", request)
    monkeypatch.setattr(agent_module, "LLMClient", lambda model_name=None: client)
    context = AgentContext()
    asyncio.run(agent_module.BaselineAgent(logs_dir=tmp_path).run(
        "complete the task", Environment(), context,
    ))

    assert commands == ([COMMAND] if executes else [])
    history = [m["content"] for m in context.metadata["messages"] if m["role"] == "assistant"]
    raw = content or ""
    if finish_reason == "length" and raw:
        expected = _tail(raw, REASONING_TAIL_CHARS)
    elif finish_reason == "length":
        expected = _tail(reasoning, REASONING_TAIL_CHARS)
    else:
        expected = raw
    assert history[0] == expected
