# Running on Windows (WSL2)

Worth doing: the task images are x86, so a Windows PC runs them natively.
Apple Silicon emulates them, which is slower and makes the qemu tasks fail
outright — full 89-task scoring runs should happen here, not on a Mac.

Everything below runs in the Ubuntu terminal, **not PowerShell**.

## 1. WSL2 and Docker

In PowerShell as Administrator:

```powershell
wsl --install
```

Reboot, finish the Ubuntu first-run setup, then install Docker Desktop for
Windows and turn on WSL2 integration (Settings → Resources → WSL integration →
enable your Ubuntu distro). Give Docker at least 30 GB of disk: the 89 task
images are large.

Check it from Ubuntu:

```bash
docker run hello-world
```

## 2. Keep the repo inside WSL

```bash
cd ~ && git clone https://github.com/canyang25/BadgerForge.git
```

**Not** under `/mnt/c/...`. Docker file access across the Windows/Linux
boundary is slow enough to distort every timing measurement you take.

## 3. Python and the agent

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd ~/BadgerForge
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
```

## 4. Tasks

```bash
git clone https://github.com/harbor-framework/terminal-bench-2-1.git ~/terminal-bench-2-1
```

Point `TB_TASKS` at it, since the run script defaults to the macOS path:

```bash
export TB_TASKS=~/terminal-bench-2-1/tasks
```

## 5. VPN and the key

GlobalProtect runs on Windows; WSL inherits the tunnel, nothing to install in
Ubuntu. Check the gateway from Ubuntu — 401 means reachable:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://llm-gw01.doit.wisc.edu/v1/models
```

1Password CLI is the fiddly part. Install the Windows desktop app, then in
Settings → Developer enable **both** "Integrate with 1Password CLI" and the
WSL option. Install `op` inside Ubuntu and check it sees your account:

```bash
op whoami
```

Then copy the template and fill in your own item:

```bash
cp .env.op .env.op.local     # LLM_API_KEY=op://Employee/<your item>/credential
```

## 6. Run

```bash
./scripts/run_task.sh regex-log
```

A full scoring run — all 89 tasks, one attempt each, as the rules require —
takes several hours. Don't let the machine sleep:

```bash
op run --env-file=.env.op.local -- \
  harbor run -p "$TB_TASKS" --agent agent.agent:BaselineAgent \
  --n-attempts 1 -n 3 -o jobs/full
python scripts/score.py jobs/full/<job-id>
```

Windows sleeps on its own schedule; set power mode to never sleep first
(`powercfg /change standby-timeout-ac 0` in an admin PowerShell) — the WSL
equivalent of the `caffeinate -i` we use on macOS.
