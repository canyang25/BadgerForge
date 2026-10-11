"""LLM client — talks to any OpenAI-compatible chat completions endpoint.

This is the layer between the agent loop (agent.py) and your model server.
It uses the ``openai`` Python library's async client, which speaks the
`OpenAI Chat Completions API <https://platform.openai.com/docs/api-reference/chat>`_.
Any server that implements this API works:

- **Ollama** (``http://localhost:11434/v1``) — easiest local option
- **vLLM** (``http://localhost:8000/v1``) — faster, supports batching + multi-GPU
- **llama.cpp server** — lightweight C++ inference
- **Cloud APIs** — Together, Fireworks, Groq, Amazon Bedrock, Google Vertex,
  or OpenAI itself (if you're not constrained to local models)

Configuration
=============
All settings come from environment variables (loaded from ``.env`` via
``python-dotenv``). See ``.env.example`` for the full list:

- ``LLM_BASE_URL`` — The HTTP endpoint (default: ``http://localhost:11434/v1``).
- ``LLM_MODEL`` — Model identifier (e.g., ``qwen2.5-coder:7b``).
- ``LLM_API_KEY`` — API key. Ollama ignores this, but the OpenAI client
  library requires a non-empty string, so use any placeholder like ``"ollama"``.
- ``LLM_TEMPERATURE`` — Sampling temperature (default: 0.2). Lower = more
  deterministic.
- ``LLM_MAX_TOKENS`` — Max tokens per completion, thinking included
  (default: 16384).

Model name resolution
=====================
Harbor's ``-m`` flag uses litellm-style prefixed names like
``ollama/qwen2.5-coder:32b``. But the OpenAI API expects the bare model ID
(``qwen2.5-coder:32b``). ``_resolve_model()`` strips known provider prefixes
so both styles work transparently.

Improvement ideas
=================
- Add retry logic with exponential backoff for transient failures.
- Add streaming support for faster time-to-first-token.
- Route different task types to different models (e.g., a small model for
  simple commands, a large model for complex reasoning).
- Track and enforce a token budget per task.
"""

import asyncio
import os

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, InternalServerError, RateLimitError

# override=True makes .env the single source of truth: without it, a stale
# copy of these variables exported into your shell (e.g. by the one-off
# `set -a; source starter/.env` used to curl-test an endpoint) silently
# shadows every later edit to the file. To experiment with settings, edit
# .env — or pass -m to harbor run for the model.
load_dotenv(override=True)

RETRYABLE_ERRORS = (
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    InternalServerError,
)
"""Failures worth retrying: the gateway is busy, asleep, or briefly unreachable."""

REASONING_TAIL_CHARS = 2000
"""How much of a cut-off response to keep. Enough to show the model where it
ran out of budget, small enough that resending it every turn costs little."""

RETRY_BASE_DELAY_SEC = 2.0
RETRY_MAX_DELAY_SEC = 60.0

_PROVIDER_PREFIXES = (
    "ollama/",
    "openai/",
    "hosted_vllm/",
    "together_ai/",
    "fireworks_ai/",
    "groq/",
)
"""Litellm-style provider prefixes that Harbor's ``-m`` flag may prepend
to model names. We strip these before sending to the OpenAI API."""


def _resolve_model(model_name: str | None) -> str:
    """Determine the model ID to use, stripping any provider prefix.

    Priority: ``LLM_MODEL`` env var > ``model_name`` argument (which comes
    from Harbor's ``-m`` flag via ``self.model_name`` on the agent).

    Raises ``ValueError`` if no model is configured anywhere.
    """
    model = os.environ.get("LLM_MODEL") or model_name
    if not model:
        raise ValueError(
            "No model configured. Set LLM_MODEL in .env or pass -m to harbor run."
        )
    for prefix in _PROVIDER_PREFIXES:
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


def _tail(text: str, limit: int) -> str:
    """Keep the last `limit` characters, flagged so the model knows why."""
    if len(text) <= limit:
        return text
    return (
        "[your previous response was cut off — you spent the whole output "
        f"budget thinking. Last {limit} characters:]\n...{text[-limit:]}"
    )


class LLMClient:
    """Async client for OpenAI-compatible chat completions.

    Instantiated once per task in ``BaselineAgent.run()``. Reads all
    configuration from environment variables at init time.

    Parameters
    ----------
    model_name : str or None
        Optional model name passed through from Harbor's ``-m`` flag.
        Overridden by ``LLM_MODEL`` env var if set.
    """

    def __init__(self, model_name: str | None = None):
        base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
        api_key = os.environ.get("LLM_API_KEY", "none")
        self.model = _resolve_model(model_name)
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "16384"))
        # BadgerBrain wakes the GPU on the first request after an idle period,
        # which takes ~90s; the quickstart asks for a 300s floor. Retries cover
        # the rest: a dropped VPN or a 429 from a busy gateway killed 16 of 21
        # trials in our first baseline run, each one losing a whole task.
        # Unset means the server's default, which on BadgerBrain is the
        # highest setting: the model spends its whole completion budget
        # thinking, the reply comes back truncated, and we get no command out
        # of the turn. Set LLM_REASONING_EFFORT to trade thinking for
        # instructions actually being followed — measure before changing it.
        self.reasoning_effort = os.environ.get("LLM_REASONING_EFFORT") or None
        self.timeout = float(os.environ.get("LLM_TIMEOUT_SEC", "300"))
        self.max_retries = int(os.environ.get("LLM_MAX_RETRIES", "5"))
        # Whether the last reply hit max_tokens. The agent nudges a cut-off
        # reply differently from one that ended without a command.
        self.last_truncated = False
        self._client = AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=self.timeout, max_retries=0
        )

    async def chat(
        self, messages: list[dict], temperature: float | None = None
    ) -> tuple[str, dict]:
        """Send the conversation history to the LLM and get a response.

        Parameters
        ----------
        messages : list[dict]
            OpenAI-format message list, e.g.::

                [
                    {"role": "system", "content": "You are..."},
                    {"role": "user", "content": "Build the Cython ext..."},
                    {"role": "assistant", "content": "```bash\\nls /app\\n```"},
                    {"role": "user", "content": "Command output:\\n..."},
                ]

        temperature : float or None
            Overrides ``LLM_TEMPERATURE`` for this request only.

        Returns
        -------
        tuple[str, dict]
            A 2-tuple of:
            - **text** — The assistant's response content (str).
            - **usage** — Token counts dict with keys ``"prompt_tokens"``
              and ``"completion_tokens"`` (both int). Empty dict if the
              server doesn't report usage.
        """
        response = await self._request_with_retries(messages, temperature)
        message = response.choices[0].message
        text = message.content or ""
        truncated = response.choices[0].finish_reason == "length"
        self.last_truncated = truncated
        if not text:
            # Reasoning models stream thinking into `reasoning_content` and
            # only fill `content` once the thinking closes. When generation
            # hits max_tokens mid-thought, `content` is empty and all we have
            # is an unfinished thought.
            #
            # We keep only its tail, and only so the model can see where it
            # ran out of room. Storing the whole thing is what wrecked our
            # baseline: 29k characters of unfinished reasoning per turn, resent
            # on every later turn, with the model eventually emitting the same
            # truncated thought nine times in a row.
            thinking = getattr(message, "reasoning_content", None) or ""
            text = _tail(thinking, REASONING_TAIL_CHARS)
        elif truncated:
            text = _tail(text, REASONING_TAIL_CHARS)
        usage = {}
        if response.usage is not None:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
            }
        return text, usage

    async def _request_with_retries(
        self, messages: list[dict], temperature: float | None = None
    ):
        """Send one request, retrying transient failures with exponential backoff.

        Retries timeouts, connection errors, rate limits and 5xx — the failures
        that come from the gateway or the network rather than from our request.
        Anything else (a bad key, a bad model name) raises immediately, because
        retrying it just wastes the task's time budget.
        """
        delay = RETRY_BASE_DELAY_SEC
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature if temperature is None else temperature,
                    max_tokens=self.max_tokens,
                    **self.extra_params(),
                )
            except RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                await asyncio.sleep(delay)
                delay = min(delay * 2, RETRY_MAX_DELAY_SEC)
        raise last_error

    def extra_params(self) -> dict:
        """Optional request fields, omitted entirely when unset.

        Sending `reasoning_effort=None` is not the same as leaving it out —
        some servers reject the explicit null — so build the dict instead.
        """
        if self.reasoning_effort:
            return {"reasoning_effort": self.reasoning_effort}
        return {}
