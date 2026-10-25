"""What happens when the model spends its whole budget thinking.

Our baseline lost polyglot-c-py this way: 8k output tokens of unfinished
reasoning per turn, stored whole, resent every turn, the same truncated
thought emitted nine times, 1.07M tokens spent, task timed out.
"""

import asyncio
from types import SimpleNamespace

from agent.llm import LLMClient, REASONING_TAIL_CHARS, _tail
from agent.tools import parse_action


def _chat(monkeypatch, content, reasoning, finish_reason):
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test")
    client = LLMClient()

    async def request(*args):
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=content, reasoning_content=reasoning),
                finish_reason=finish_reason,
            )],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

    monkeypatch.setattr(client, "_request_with_retries", request)
    text, usage = asyncio.run(client.chat([]))
    return client, text, usage


def test_truncated_content_is_returned_whole(monkeypatch):
    content = "```bash\n" + ("echo line\n" * 400) + "```"
    client, text, usage = _chat(monkeypatch, content, "```bash\necho draft\n```", "length")
    assert text == content
    assert parse_action(text).kind == "shell"
    assert "echo line" in parse_action(text).command
    assert client.last_truncated is True
    assert client.reasoning_tail == ""
    assert usage == {"prompt_tokens": 10, "completion_tokens": 5}


def test_a_cut_off_thinking_scrap_is_not_an_action(monkeypatch):
    reasoning = ("thinking " * 400) + "\n```bash\necho draft\n```"
    client, text, _ = _chat(monkeypatch, None, reasoning, "length")
    assert text == ""
    assert parse_action(text).kind == "none"
    assert client.last_truncated is True
    assert client.reasoning_tail == _tail(reasoning, REASONING_TAIL_CHARS)
    assert "echo draft" in client.reasoning_tail


def test_finished_reasoning_is_not_kept_or_executed(monkeypatch):
    client, text, _ = _chat(monkeypatch, "", "```bash\necho draft\n```", "stop")
    assert text == ""
    assert parse_action(text).kind == "none"
    assert client.last_truncated is False
    assert client.reasoning_tail == ""


def test_short_response_is_left_alone():
    assert _tail("ls /app", REASONING_TAIL_CHARS) == "ls /app"


def test_long_response_is_cut_to_its_tail():
    thinking = "".join(f"step {i} " for i in range(5000))
    kept = _tail(thinking, REASONING_TAIL_CHARS)
    assert len(kept) < len(thinking) / 10
    assert kept.endswith(thinking[-200:])


def test_the_model_is_told_why_its_text_is_missing():
    kept = _tail("x" * 10_000, REASONING_TAIL_CHARS)
    assert "cut off" in kept
    assert "output budget" in kept


def test_a_full_turn_of_thinking_costs_about_one_percent_as_much():
    # 29,625 chars is what one turn actually cost us in the baseline.
    before = 29_625
    after = len(_tail("x" * before, REASONING_TAIL_CHARS))
    assert after < before * 0.1
