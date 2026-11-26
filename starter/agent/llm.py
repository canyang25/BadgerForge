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
- ``LLM_MAX_TOKENS`` — Max tokens per completion (default: 2048).

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

import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

# override=True makes .env the single source of truth: without it, a stale
# copy of these variables exported into your shell (e.g. by the one-off
# `set -a; source starter/.env` used to curl-test an endpoint) silently
# shadows every later edit to the file. To experiment with settings, edit
# .env — or pass -m to harbor run for the model.
load_dotenv(override=True)

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
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "2048"))
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def chat(self, messages: list[dict]) -> tuple[str, dict]:
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

        Returns
        -------
        tuple[str, dict]
            A 2-tuple of:
            - **text** — The assistant's response content (str).
            - **usage** — Token counts dict with keys ``"prompt_tokens"``
              and ``"completion_tokens"`` (both int). Empty dict if the
              server doesn't report usage.
        """
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        message = response.choices[0].message
        text = message.content or ""
        if not text:
            # Reasoning models (e.g. served behind vLLM's reasoning parser)
            # stream their thinking into `reasoning_content` and only fill
            # `content` once the thinking closes. If generation hits
            # max_tokens mid-thought, `content` comes back empty every turn
            # and the agent loops on nudges until the task times out. Fall
            # back to the (truncated) thinking text — it often contains a
            # usable command, and it makes the failure visible in the
            # transcript. The real fix is a larger LLM_MAX_TOKENS.
            text = getattr(message, "reasoning_content", None) or ""
        usage = {}
        if response.usage is not None:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
            }
        return text, usage
