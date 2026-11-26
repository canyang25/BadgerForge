# UW–Madison hosted endpoint

UW–Madison runs a shared model gateway (BadgerBrain) on campus GPUs, so UW–Madison participants can compete without a GPU of their own. This page explains how your agent connects to it. The gateway's own docs are the source of truth and are updated when models change: [BadgerBrain gateway quickstart](https://github.com/qualiaMachine/BadgerBrain/blob/main/docs/gateway-quickstart.md).

## How the pieces fit

Your agent never loads a model itself. The starter's `agent/llm.py` reads three values from `.env` and sends OpenAI-style chat requests over HTTP:

```
your agent (llm.py)  ──HTTP──▶  LLM_BASE_URL  (the gateway)
        │                             │
   LLM_API_KEY                   LLM_MODEL
   (sent as a Bearer token       (which model you're asking
    to prove you're allowed)      the gateway to run)
```

- **`LLM_BASE_URL`**: `https://llm-gw01.doit.wisc.edu/v1`. It speaks the OpenAI API.
- **`LLM_MODEL`**: the model name *as the gateway knows it*. It must match what `GET /v1/models` reports, not a name you choose. The chat model is currently `qwen3.8-27b`.
- **`LLM_API_KEY`**: your personal gateway key. Requests without it are rejected.

## Before you start: network access

Two things have to be true before any request gets through:

1. **You're on GlobalProtect (the campus VPN)**, including when you're on campus wifi.
2. **Your NetID has been added to the gateway's firewall rule.** Access is granted per person, so the VPN alone isn't enough. This happens when you request a key (next section). Someone has to do it by hand, so allow some lead time.

Both failures look the same: the request hangs, or you get `Unable to connect to the remote server`. To check the network before you have a key:

```bash
# 401 = you reached the gateway and it wants a key, which is what you want here.
# A hang or connection error = VPN or firewall.
curl -s -o /dev/null -w "%{http_code}\n" --max-time 10 \
  https://llm-gw01.doit.wisc.edu/v1/models
```

If DNS fails, reconnect GlobalProtect. If DNS resolves but the connection hangs, your NetID probably isn't in the firewall rule yet. The [gateway quickstart](https://github.com/qualiaMachine/BadgerBrain/blob/main/docs/gateway-quickstart.md#network-access) has a PowerShell check (`Test-NetConnection`) that tells the two cases apart.

## Get a key

Request one through the [BadgerBrain access form](https://forms.gle/vkcLzApNrX7KbkTP9). It asks for your group or project (say you're competing in the ML Marathon) and your NetID, which is used for the firewall rule. The key arrives as a **1Password share link** tied to your `@wisc.edu` address. Save it into your UW–Madison 1Password account; the [gateway quickstart](https://github.com/qualiaMachine/BadgerBrain/blob/main/docs/gateway-quickstart.md#step-1--get-your-key-and-save-it) covers setting that account up. The link expires, so if it has expired or you lose the key, request another through the same form.

The key identifies you: every request is logged against it. Don't commit it, paste it into a notebook, or share it with teammates. Each team member should request their own.

## Configure `.env`

The `.env` file lives in the `starter/` directory. When Harbor starts your agent, `agent/llm.py` loads `starter/.env` automatically (via `python-dotenv`), so you never pass these values on the command line. `starter/.env` is gitignored. Create it from the template, then fill in your key:

```bash
# run from the repo root
cp starter/.env.example starter/.env
```

```bash
# starter/.env — UW–Madison gateway (key required; GlobalProtect + firewall access required)
LLM_BASE_URL=https://llm-gw01.doit.wisc.edu/v1
LLM_MODEL=qwen3.8-27b
LLM_API_KEY=<your gateway key>
LLM_MAX_TOKENS=8192
```

The gateway docs name the variable `OPENAI_API_KEY`. The starter reads `LLM_API_KEY` instead, so put the same key there. Because the starter loads `.env` with `override=True`, the value in `starter/.env` wins over anything exported in your shell.

## Verify the connection

One command checks the VPN, the firewall, your key, and prints the exact `LLM_MODEL` string. `.env` is read by the *agent*, not by your terminal, so for this one-off check you first have to load the file into your shell. Run both lines from the repo root:

```bash
set -a; source starter/.env; set +a    # load .env values into this shell session
curl -s "$LLM_BASE_URL/models" -H "Authorization: Bearer $LLM_API_KEY"
```

- **JSON listing models**: you're connected. Use the chat model's `id` as `LLM_MODEL`.
- **401 / `Invalid proxy key`**: the key is wrong, missing, or expired.
- **`Malformed API Key`**: the key didn't make it into the header. Check that `LLM_API_KEY` is set in `starter/.env` and that you ran the `source` line.
- **`404 ... Model Group=...`** (from the agent): `LLM_MODEL` has a typo, or the model was swapped out. Re-check `/models`.
- **Hang / connection error**: VPN or firewall. See [network access](#before-you-start-network-access).

To see your key's limits and how much it has used so far:

```bash
curl -s https://llm-gw01.doit.wisc.edu/key/info -H "Authorization: Bearer $LLM_API_KEY"
```

## Things to know about this endpoint

- **Always use the gateway URL.** You may come across a direct model hostname ending in `deepthought.doit.wisc.edu`. Don't use it: those hosts bypass the gateway, so your usage isn't tracked there.
- **The catalogue changes.** Models are occasionally swapped in and out. If a model name stops working, check `/v1/models` and the [gateway quickstart](https://github.com/qualiaMachine/BadgerBrain/blob/main/docs/gateway-quickstart.md). On your *submission card*, the gateway's `qwen3.8-27b` corresponds to the approved anchor checkpoint `Qwen/Qwen3.8-27B-FP8`.
- **It's a reasoning model.** Thinking tokens count against the completion budget, and the model writes its final answer (`content`) only after it finishes thinking. If the budget runs out mid-thought, the response comes back *empty*. Set `LLM_MAX_TOKENS=8192`. At the starter default of 2048 (and sometimes 4096), every turn comes back empty, the agent loops on nudge messages, and the task fails with `AgentTimeoutError`. Thinking arrives in `reasoning_content`, separate from the final `content`. See the matching entry in [troubleshooting.md](troubleshooting.md).
- **Set a generous timeout.** `qwen3.8-27b` normally stays loaded. Other gateway models release their GPU when idle and take about 90 seconds to start again on the first request. If your first call is slow and your second is fast, that was a cold start, not a fault.
- **Token usage still costs points.** Every million tokens costs 0.01 leaderboard points, so lean context management pays.
- **Capacity is shared.** The gateway runs on two GPUs that serve every team plus other campus users. Keep `harbor run -n` at 2–4. If you get a 429 (rate limited), back off and retry. Post a heads-up in the Kaggle Discussion tab before starting a full 89-task sweep.
- **Public data only.** The gateway is a pilot service. Don't send it anything that isn't public; the task repos are fine.
