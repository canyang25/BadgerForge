# Bring your own model

The baseline talks to any **OpenAI-compatible** chat completions endpoint. Set three values in `.env`:

```bash
LLM_BASE_URL=...   # where the endpoint lives
LLM_MODEL=...      # model id as the endpoint knows it
LLM_API_KEY=...    # anything non-empty for local endpoints
```

## Provided endpoint (UW–Madison participants)

UW–Madison participants can use the provided hosted gateway — setup, verification, and usage notes in [uw_madison_endpoint.md](uw_madison_endpoint.md).

## Ollama (easiest local option)

Covered end-to-end in [walkthrough.md Step 5](walkthrough.md#step-5-set-up-a-model-endpoint) — install, pull a model sized for your GPU, verify, configure `.env`. Tip: `ollama list` shows the exact model names to use in `LLM_MODEL`.

## vLLM (serious local serving)

Higher throughput and better parallelism than Ollama — worth it once you're running full subsets.

```bash
uv pip install vllm
vllm serve Qwen/Qwen2.5-Coder-32B-Instruct-AWQ --max-model-len 16384
```

```bash
# .env
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
LLM_API_KEY=none
```

## Hosted open-weight APIs (no GPU needed)

Together, Fireworks, and Groq all serve open-weight models behind OpenAI-compatible endpoints — handy for development before you have local hardware. Example (Together):

```bash
# .env
LLM_BASE_URL=https://api.together.xyz/v1
LLM_MODEL=Qwen/Qwen2.5-Coder-32B-Instruct
LLM_API_KEY=<your-together-key>     # use a throwaway/dev key
```

**Constraint reminder:** hosted endpoints are fine for *development*, but your submitted run must use one of the approved models on the [competition page](https://www.kaggle.com/competitions/OpenAgent-Coding/overview). Closed-weight models (GPT, Claude, Gemini) are out of scope everywhere. Bedrock's fully-managed `qwen3-coder-30b-a3b` counts as the approved FP8 entry; Bedrock Custom Model Import is not viable for a hackathon team (Provisioned-Throughput-only, $21–50/hr). Anchor: `Qwen/Qwen3.8-27B-FP8` (~37 GB) — the [provided UW–Madison endpoint](uw_madison_endpoint.md), or self-host it from HuggingFace; the most widely hosted alternative is `Qwen/Qwen2.5-Coder-32B-Instruct-AWQ` (28 GB).

## Swapping models

Everything is `.env`-driven — swap models as often as you like during the competition. You can also pass `-m provider/model` to `harbor run` to record which model a job used (the agent strips the provider prefix automatically; `LLM_MODEL` takes precedence if both are set).
