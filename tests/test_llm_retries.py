"""The retry path, exercised without touching the network.

The first baseline run lost 16 of 21 trials to APITimeoutError, so this is
the behaviour we care most about not regressing.
"""

import asyncio

import httpx
import pytest
from openai import APITimeoutError, AuthenticationError

from agent.llm import LLMClient


def make_client(monkeypatch, **env) -> LLMClient:
    monkeypatch.setenv("LLM_MODEL", "qwen3.8-27b")
    monkeypatch.setenv("LLM_API_KEY", "test")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    client = LLMClient()
    monkeypatch.setattr(asyncio, "sleep", _no_wait)
    return client


async def _no_wait(_seconds):
    return None


class FakeCompletions:
    """Fails `failures` times, then returns `result`."""

    def __init__(self, failures, result=None, error=None):
        self.failures = failures
        self.result = result
        self.error = error or APITimeoutError(request=httpx.Request("POST", "http://x"))
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return self.result


def install(client, fake):
    client._client.chat.completions = fake
    return fake


def test_defaults_match_the_gateway_guidance(monkeypatch):
    client = make_client(monkeypatch)
    assert client.timeout == 300.0
    assert client.max_retries == 5


def test_retries_then_succeeds(monkeypatch):
    client = make_client(monkeypatch)
    fake = install(client, FakeCompletions(failures=3, result="ok"))
    assert asyncio.run(client._request_with_retries([])) == "ok"
    assert fake.calls == 4


def test_gives_up_after_max_retries(monkeypatch):
    client = make_client(monkeypatch, LLM_MAX_RETRIES="3")
    fake = install(client, FakeCompletions(failures=99))
    with pytest.raises(APITimeoutError):
        asyncio.run(client._request_with_retries([]))
    assert fake.calls == 3


def test_does_not_retry_a_bad_key(monkeypatch):
    client = make_client(monkeypatch)
    auth_error = AuthenticationError(
        "invalid key",
        response=httpx.Response(401, request=httpx.Request("POST", "http://x")),
        body=None,
    )
    fake = install(client, FakeCompletions(failures=99, error=auth_error))
    with pytest.raises(AuthenticationError):
        asyncio.run(client._request_with_retries([]))
    assert fake.calls == 1
