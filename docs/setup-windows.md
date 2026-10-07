# Running on Windows (WSL2)

Full 89-task runs belong here, not on a Mac: the task images are x86, so
Windows runs them natively, while Apple Silicon emulates them (slower) and
can't run the two qemu tasks at all. A full run takes **8–12 hours** — 17
tasks allow 30+ minutes and one allows 200 — so plan it overnight.

Everything from step 4 on runs in the Ubuntu terminal, **not PowerShell**.

## 0. How much memory?

Settings → System → About → Installed RAM. Eight tasks ask for 8 GB each, and
WSL only gets what you give it.

| Installed RAM | `.wslconfig` memory | `N_CONCURRENT` |
|---|---|---|
| 32 GB | 24GB | 3 |
| 16 GB | 12GB | 2 (expect 12+ hours) |

## 1. WSL2

PowerShell as Administrator: `wsl --install`, reboot, finish the Ubuntu setup.

Create `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
memory=24GB
networkingMode=mirrored
```

Then `wsl --shutdown` in PowerShell so it takes effect. `mirrored` matters:
with WSL's default networking, GlobalProtect often leaves Ubuntu unable to
reach campus hosts. (Needs Windows 11 22H2 or later.)

## 2. Docker Desktop

Install it, then Settings → Resources → WSL integration → turn on Ubuntu.
Give it ~100 GB of disk; the images for 89 tasks add up. From Ubuntu:

```bash
docker run hello-world
```

## 3. 1Password

1. Windows desktop app, signed in to `uw-madison.1password.com`.
   Settings → Developer → **Integrate with 1Password CLI**.
2. PowerShell: `winget install AgileBits.1Password.CLI`
3. From Ubuntu (a new terminal, so PATH picks it up): `op.exe whoami`

1Password documents no WSL integration. WSL can run Windows programs, so
`scripts/env.sh` calls `op.exe`, and the key lives only in that shell's
environment, never in a file.

## 4. Repo, Python, tasks

Inside WSL, **not** under `/mnt/c/...` — file access across that boundary is
slow enough to distort every timing.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.bashrc
cd ~ && git clone https://github.com/canyang25/BadgerForge.git && cd BadgerForge
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]" && pytest -q
git clone https://github.com/harbor-framework/terminal-bench-2-1.git ~/terminal-bench-2-1
cp .env.op .env.op.local     # then set LLM_API_KEY=op://Employee/<your item>/credential
```

## 5. Check each piece

GlobalProtect connected on Windows first.

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://llm-gw01.doit.wisc.edu/v1/models   # 401
source scripts/env.sh && echo "key length ${#LLM_API_KEY}"                          # never echo the key
TB_TASKS=~/terminal-bench-2-1/tasks ./scripts/run_task.sh regex-log                 # 5-10 min
```

## 6. Before the long run

- Plugged in. In an Administrator PowerShell:
  ```powershell
  powercfg /change standby-timeout-ac 0
  powercfg /change hibernate-timeout-ac 0
  powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
  powercfg /setactive SCHEME_CURRENT
  ```
  (no sleep, no hibernate, closing the lid does nothing)
- Pause Windows Update so it doesn't restart overnight.
- GlobalProtect connected.

## 7. Full run

Inside `tmux`, so closing the terminal doesn't kill the run:

```bash
tmux new -s full
cd ~/BadgerForge && source .venv/bin/activate
N_CONCURRENT=3 ./scripts/run_full.sh
```

Detach with `Ctrl-b d`, reattach with `tmux attach -t full`. If it stops —
VPN drop, reboot — resume, which skips finished trials and re-runs the ones
that failed on the gateway connection:

```bash
./scripts/run_full.sh resume jobs/full-<timestamp>
```

## 8. Afterwards

```bash
python scripts/score.py jobs/full-<timestamp>
./scripts/export_trials.py jobs/full-<timestamp> --out eval/results/full-<date>-trials.csv
```

Commit the CSV on a branch and open a PR. It's what the next dev slice is
picked from, and it lets anyone analyse the run without the Windows machine.
