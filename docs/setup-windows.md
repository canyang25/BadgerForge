# Running on Windows (WSL2)

Full 89-task runs belong here, not on a Mac: the task images are x86, so
Windows runs them natively, while Apple Silicon emulates them (slower) and
can't run the two qemu tasks at all. A full run takes **8–12 hours** — 17
tasks allow 30+ minutes and one allows 200 — so plan it overnight. The
2026-10-07 run took 11 h on a 16 GB laptop at concurrency 2, including one
restart.

Steps 4–6 run in the Ubuntu terminal. The run itself (step 7) starts from
PowerShell, because of 1Password (step 3).

## 0. How much memory?

Settings → System → About → Installed RAM. Eight tasks ask for 8 GB each, and
WSL only gets what you give it. harbor itself is the other consumer: it keeps
every finished trial in memory and passed 11 GB around task 56 of 89, which is
what the swap line in step 1 is for. Without swap the OOM killer takes harbor
down and the run stops.

| Installed RAM | `.wslconfig` memory | swap | `N_CONCURRENT` |
|---|---|---|---|
| 32 GB | 24GB | 8GB | 3 |
| 16 GB | 12GB | 8GB | 2 (about 11 hours) |

## 1. WSL2

PowerShell as Administrator: `wsl --install`, reboot, then
`wsl --install -d Ubuntu-24.04`. Create `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
memory=12GB
swap=8GB
networkingMode=mirrored

[experimental]
autoMemoryReclaim=gradual
```

Then `wsl --shutdown` in PowerShell so it takes effect. `mirrored` matters:
with WSL's default networking, GlobalProtect often leaves Ubuntu unable to
reach campus hosts. (Needs Windows 11 22H2 or later.) `autoMemoryReclaim`
hands page cache back to Windows: without it the VM sits at its full
allowance after the first image builds and Windows starts paging — the
symptom is `wsl` commands failing with `WSAETIMEDOUT` while the run inside
keeps going (see Troubleshooting).

## 2. Docker Desktop

Install it, then Settings → Resources → WSL integration → turn on Ubuntu.
Give it ~100 GB of disk; the images for 89 tasks add up. From Ubuntu:

```bash
docker run hello-world
```

## 3. 1Password

1. Windows desktop app, signed in to `uw-madison.1password.com` and unlocked.
   Settings → Developer → **Integrate with 1Password CLI**, then quit the app
   from the tray and reopen it — the setting only takes effect after a restart.
2. PowerShell: `winget install AgileBits.1Password.CLI`. If `op.exe --version`
   then says not found, add the package folder under
   `%LOCALAPPDATA%\Microsoft\WinGet\Packages` to your PATH.
3. PowerShell: `op.exe read "op://Employee/<your item>/credential" | Measure-Object -Character`.
   Click **Allow** in 1Password; you should get a character count, never the key.

The app authorizes every `op.exe` call with a prompt and only remembers the
answer with Windows Hello set up. Calls made from inside WSL never get
through: they time out after 60 s with "authorization timeout" or "cannot
connect to 1Password app", so `env.sh` cannot resolve the key there. Instead
`scripts\run_full_windows.ps1` reads it on the Windows side — one Allow click
per start or resume — and passes it to the WSL shell through `WSLENV`;
`env.sh` keeps an `LLM_API_KEY` that is already in the environment. The key
only ever lives in that tmux session's environment.

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

If `apt-get update` hangs first, `archive.ubuntu.com` is unreachable from
that network; point `/etc/apt/sources.list.d/ubuntu.sources` at a mirror.

## 5. Check each piece

GlobalProtect connected on Windows first. From Ubuntu:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://llm-gw01.doit.wisc.edu/v1/models   # 401
```

Then one task from PowerShell, which also proves the 1Password step
(5–10 minutes; click Allow when asked):

```powershell
powershell -ExecutionPolicy Bypass -File \\wsl.localhost\Ubuntu-24.04\home\<you>\BadgerForge\scripts\run_full_windows.ps1 task regex-log
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
- Close browsers, game launchers and chat apps. The 16 GB laptop was down to
  0.3 GB free at the worst point with them open.
- GlobalProtect connected.

## 7. Full run

From PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File \\wsl.localhost\Ubuntu-24.04\home\<you>\BadgerForge\scripts\run_full_windows.ps1
```

Click Allow in 1Password within 60 s. The run lives in a tmux session named
`full` inside Ubuntu (`-Concurrent 3` for the 32 GB row). Watch it without
attaching:

```bash
./scripts/full_progress.sh    # done/pass counts, whether harbor is alive, log age
```

or `wsl -d Ubuntu-24.04 -- tmux attach -t full` (`Ctrl-b d` to leave). If it
stops — VPN drop, reboot, OOM — resume. It skips finished trials, reruns
unfinished ones (any trial directory without a `result.json`) and the ones
that failed on the gateway or on authentication. To redo a finished trial,
delete its directory first. After a reboot, start Docker Desktop and connect
GlobalProtect before resuming.

```powershell
powershell -ExecutionPolicy Bypass -File ...\scripts\run_full_windows.ps1 resume jobs/full-<timestamp>
```

## 8. Afterwards

harbor puts the trials in a timestamped directory under the job directory;
`score.py` wants that inner one, `export_trials.py` takes either.

```bash
python scripts/score.py jobs/full-<timestamp>/<harbor job id>
./scripts/export_trials.py jobs/full-<timestamp> --out eval/results/full-<date>-trials.csv
```

Commit the CSV on a branch and open a PR. It's what the next dev slice is
picked from, and it lets anyone analyse the run without the Windows machine.

## Troubleshooting

- **`wsl` commands fail with `Wsl/Service/WSAETIMEDOUT` but the run goes on.**
  Windows is out of memory; the VM is holding page cache. `wsl -l -v` still
  answers. Hand the cache back:
  `wsl -d Ubuntu-24.04 -u root -- sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'`,
  and check `.wslconfig` has the swap and `autoMemoryReclaim` lines.
- **`tmux ls` shows `full` but nothing moves.** The session outlives harbor.
  `full_progress.sh` prints `harbor=NO`; the end of `jobs/full-run.log` says
  `run exited`. Resume.
- **harbor was OOM-killed** (`dmesg | grep -i oom` inside Ubuntu names it):
  the swap line is missing. Add it, `wsl --shutdown`, restart Docker Desktop,
  resume.
- **Calling `wsl.exe` from Git Bash with a `/mnt/c/...` argument** rewrites
  the path; prefix the command with `MSYS_NO_PATHCONV=1`.
- **Progress from the Windows side**, without entering the distro:
  `Get-Content \\wsl.localhost\Ubuntu-24.04\home\<you>\BadgerForge\jobs\full-run.log -Tail 5`.
