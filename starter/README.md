# Coding Agent Starter

This directory contains a minimal working agent (~200 lines) wired into [Harbor](https://www.harborframework.com/), the official Terminal-Bench 2.0 evaluation framework. Your job is to make it better.

**Setup and first run:** follow [docs/walkthrough.md](docs/walkthrough.md) — fresh machine to a scored baseline run in ~30 minutes. Challenge rules, approved models, and scoring: [competition page](https://www.kaggle.com/competitions/OpenAgent-Coding/overview).

## Layout

| Path | What it is |
|---|---|
| `agent/agent.py` | The ReAct loop: instruction → ask LLM → parse one bash block → execute in container → repeat until `TASK_COMPLETE` or budget exhausted |
| `agent/prompts.py` | System prompt + message templates |
| `agent/tools.py` | Parses model output into actions, runs commands |
| `agent/llm.py` | Talks to the model endpoint (`.env`-configured) |
| `eval/public_subset.txt` | Task names for `./scripts/run_subset.sh` |
| `scripts/` | `run_baseline.sh` (sample set), `run_subset.sh` (public subset), VRAM check tools |

## Making it yours

Read `agent/agent.py` first — it's short on purpose. Where points hide, roughly in order of effort:

- **`prompts.py`** — better instructions, task-type hints, output discipline
- **Context management** — the conversation grows every turn; what do you keep, summarize, drop?
- **Error recovery** — what happens after a failed command? The baseline just shows the error and hopes
- **Planning / self-critique** — separate plan and act steps; verify before declaring done
- **Model choice + quantization** — see [docs/byo_model.md](docs/byo_model.md); fit and speed matter as much as smarts
- **Architecture** — multi-stage pipelines, retrieval, ensembles, fine-tuning, or go [installed-agent](docs/harbor.md#writing-your-own-agent) and bring custom tools

Keep your `jobs/` directories — organizers verify the top self-reported scores after the deadline by re-running your agent.

## Docs

| Doc | What's in it |
|---|---|
| [docs/walkthrough.md](docs/walkthrough.md) | **Start here.** End-to-end guide: Docker → uv → Harbor → model → first score → making changes |
| [docs/harbor.md](docs/harbor.md) | Harbor mental model, commands, custom agents, public leaderboard submission |
| [docs/byo_model.md](docs/byo_model.md) | Ollama / vLLM / hosted endpoints, `.env` config |
| [docs/uw_madison_endpoint.md](docs/uw_madison_endpoint.md) | The provided UW–Madison hosted endpoint |
| [docs/troubleshooting.md](docs/troubleshooting.md) | First-week issues, in order of likelihood |
| [docs/safety.md](docs/safety.md) | The rules that keep your laptop alive |

## License

MIT. Your submission repo must be MIT or Apache 2.0 too.
