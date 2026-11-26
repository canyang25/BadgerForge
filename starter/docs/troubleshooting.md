# Troubleshooting

Work through these in order — they cover ~90% of first-week issues. Still stuck? Post in the Kaggle Discussion tab with the exact command, the full error, and your OS.

## Setup

**`harbor: command not found`**
Your venv isn't activated (`source .venv/bin/activate` from the repo root) or the install failed. Re-run `uv pip install -e starter/` and check for errors.

**`requires-python >=3.12` / install resolution errors**
Harbor needs Python 3.12+. Recreate the venv: `uv venv --python 3.12` (uv downloads 3.12 for you if missing).

**`Failed to import module 'agent.agent'`**
The agent package isn't installed in the venv Harbor runs from. From the repo root: `uv pip install -e starter/` (the editable install is what makes `--agent agent.agent:BaselineAgent` resolvable).

**`Cannot connect to the Docker daemon`**
Docker isn't running. Start Docker Desktop (macOS/Windows) or `sudo systemctl start docker` (Linux).

**`permission denied ... docker.sock`** (Linux)
You skipped `sudo usermod -aG docker $USER` — run it, then log out and back in (or `newgrp docker`).

**Docker builds fail with "no space left on device"**
Give Docker ≥30 GB of disk. Reclaim space with `docker system prune` (careful: deletes stopped containers and unused images).

**Everything is slow on Windows**
Keep your repo inside the WSL2 filesystem (`~/...`), not `/mnt/c/...`.

**Corporate laptop / no admin rights**
You can't install Docker locally. Harbor supports cloud sandboxes (Daytona) as a fallback, or run on any Linux VM you control.

**Oracle run fails (`harbor run -d terminal-bench-sample@2.0 -a oracle`)**
This is the canary. One failed task out of 10 is usually a flake (image-pull hiccup, timing-sensitive grader) — re-run just that task with `-i <task-name>`. If most tasks fail or you see exceptions, the problem is your Docker/Harbor setup, not your agent: check Docker is running, you have disk space (≥30 GB for Docker), and your network can pull images.

## Agent runs

**Agent import fails with `--agent agent.agent:BaselineAgent`**
Activate the venv and make sure you ran `uv pip install -e starter/` from the repo root — that's what puts the `agent` package on Harbor's import path.

**Agent starts but every LLM call fails (connection refused / 404)**
Your endpoint isn't up or `.env` is wrong. Test it directly:

```bash
curl $LLM_BASE_URL/models -H "Authorization: Bearer $LLM_API_KEY"
```

If that fails, fix the endpoint before debugging the agent. Ollama default is `http://localhost:11434/v1` (note the `/v1`).

**`No model configured`**
Set `LLM_MODEL` in `.env`, or pass `-m` to `harbor run`.

**Changed `.env` but the agent behaves like it didn't**
If you ever ran `set -a; source starter/.env; set +a` (the endpoint curl check), that shell now holds exported copies of the old values. The starter loads `.env` with `override=True`, so the file wins — but if you're on an older checkout, or you exported the variables some other way, run `unset LLM_BASE_URL LLM_MODEL LLM_API_KEY LLM_MAX_TOKENS LLM_TEMPERATURE` or open a fresh terminal.

**Model replies but the agent does nothing (repeated nudge messages)**
The model isn't following the one-bash-block protocol. Common with very small models (<7B). Try a bigger/stronger coder model, lower the temperature, or tighten `prompts.py` — this is your first real agent-engineering problem, welcome.

**`AgentTimeoutError` and every assistant response is empty (reasoning models)**
The model spent its whole `LLM_MAX_TOKENS` budget thinking and never reached the final answer — vLLM's reasoning parser puts thinking in `reasoning_content`, so a mid-thought truncation leaves `content` empty, the agent nudges, and the loop repeats until the task times out. Diagnose from the trial's saved conversation:

```bash
jq -r '.agent_result.metadata.messages[] | .role + ": " + ((.content // "")[0:120])' \
  jobs/<job-id>/*/result.json | head -20
```

Empty `assistant:` lines alternating with nudges confirm it (the output token count will be exactly `turns × LLM_MAX_TOKENS`). Fix: raise `LLM_MAX_TOKENS` in `.env` — 8192 is a good starting point for reasoning models.

**Tasks time out constantly**
Local models are slow; a 5-minute task budget is tight. Check tokens/sec on your endpoint. Quantize harder, shorten `LLM_MAX_TOKENS`, trim the conversation history, or reduce `-n` concurrency so tasks aren't starving each other.

**Out of memory / machine grinding during runs**
Each concurrent task is a full container plus your model server. Drop `-n` to 1–2, and give Docker more memory in Docker Desktop settings.

## Results

**Where are my scores?**
Console prints the aggregate at the end; per-trial details are in `./jobs/<job-name>/.../result.json`.

**My score varies run to run**
Normal — LLM sampling is stochastic. The leaderboard scores a single attempt per task; use `--n-attempts` locally for pass@k stats, and report your evaluation procedure honestly in the writeup.
