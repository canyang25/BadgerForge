import asyncio
from types import SimpleNamespace

import pytest
from harbor.models.agent.context import AgentContext

import agent.agent as agent_module
from agent.llm import LLMClient, REASONING_TAIL_CHARS, _tail

COMMAND = "cat > /app/solution.py <<'PY'\n" + "# padding\n" * 240 + "print('done')\nPY"
BLOCK = f"```bash\n{COMMAND}\n```"


@pytest.mark.parametrize("content, reasoning, finish_reason, executes", [
    (BLOCK, None, "length", True),
    (BLOCK[:-3], None, "length", False),
    (BLOCK, None, "stop", True),
    (None, "thinking " * 500, "length", False),
])
def test_actions_use_full_content_and_history_is_bounded(
    monkeypatch, tmp_path, content, reasoning, finish_reason, executes
):
    text = content or reasoning
    replies = iter([(content, reasoning, finish_reason), ("TASK_COMPLETE", None, "stop")])
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test")
    client = LLMClient()

    async def request(*args):
        content, reasoning, finish = next(replies)
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=content, reasoning_content=reasoning),
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
    assert history[0] == (_tail(text, REASONING_TAIL_CHARS) if finish_reason == "length" else text)
