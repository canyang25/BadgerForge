# BadgerForge

Our team's agent for the MLM26 Efficient Coder Challenge. Scored on
Terminal-Bench 2.1 with open-weight models served by BadgerBrain.

See [plan.md](plan.md) for what we're building next and
[CONTRIBUTING.md](CONTRIBUTING.md) for how we work.

## Setup

You need Docker running, the campus VPN (GlobalProtect), and a BadgerBrain
key. Ask Chris (endemann@wisc.edu) for the key if you don't have one — it
takes a day or two and is tied to your NetID.

```bash
# 1. Python env
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Terminal-Bench 2.1 tasks
git clone https://github.com/harbor-framework/terminal-bench-2-1.git ~/Documents/terminal-bench-2-1

# 3. Check the gateway is reachable (needs VPN; 401 is the correct answer)
curl -s -o /dev/null -w "%{http_code}\n" https://llm-gw01.doit.wisc.edu/v1/models
```

### Your key

The key never goes in a file. Save the 1Password share link Chris sends into
your vault, then point `.env.op` at it:

```
LLM_API_KEY=op://Employee/<your item>/credential
```

`op vault list` and `op item list` show the names. Everything runs through
`op run`, which injects the key for that one command only.

```bash
./scripts/run_task.sh regex-log
```

Gotchas we already hit:
- A plain `.env` file overrides `op run` (the loader uses `override=True`),
  so don't create one.
- First request after an idle period waits ~90s for GPU cold start.
- `LLM_MAX_TOKENS` below ~8192 makes the reasoning model return empty
  responses and time out.
- Apple Silicon can't run the qemu tasks (x86 emulation lacks a syscall),
  and `build-cython-ext` has a broken reference solution upstream.

## Layout

See CONTRIBUTING.md. Short version: decision logic in `agent/`, prompts as
Markdown in `agent/prompts/`, benchmark scripts in `scripts/`.

The agent in `agent/` started as the challenge starter
([qualiaMachine/MLM26_EfficientCoder](https://github.com/qualiaMachine/MLM26_EfficientCoder)),
restructured to the layout above.
