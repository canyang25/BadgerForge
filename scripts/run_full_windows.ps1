# Start or resume the full run from Windows, or run one task.
#
#   .\scripts\run_full_windows.ps1                               new full job
#   .\scripts\run_full_windows.ps1 resume jobs/full-<timestamp>  continue one
#   .\scripts\run_full_windows.ps1 task regex-log                one task, foreground
#
# Why this exists: the 1Password desktop app only authorizes op.exe when it is
# called from Windows. Calls from inside WSL time out, so env.sh can't resolve
# the key there. This reads it here (click Allow in 1Password within 60 s) and
# hands it to the WSL shell through WSLENV; env.sh keeps a LLM_API_KEY that is
# already in the environment. The key lives in that shell's environment only.
#
# Run from PowerShell, with the repo cloned inside WSL (see docs/setup-windows.md):
#   powershell -ExecutionPolicy Bypass -File \\wsl.localhost\Ubuntu-24.04\home\<you>\BadgerForge\scripts\run_full_windows.ps1
param(
    [ValidateSet("start", "resume", "task")] [string]$Mode = "start",
    [string]$Arg = "",
    [string]$Distro = "Ubuntu-24.04",
    [string]$Repo = "~/BadgerForge",
    [int]$Concurrent = 2
)
$ErrorActionPreference = "Stop"
if ($Mode -ne "start" -and -not $Arg) { throw "$Mode needs an argument: the job dir (jobs/full-<timestamp>) or the task name" }

# The op:// reference comes from .env.op.local inside the repo, so the item name lives in one place.
$ref = (wsl.exe -d $Distro -- bash -c "grep '^LLM_API_KEY=op://' $Repo/.env.op.local | cut -d= -f2-" | Out-String).Trim()
if (-not $ref) { throw "$Repo/.env.op.local has no LLM_API_KEY=op://... line (copy .env.op and fill in your item)" }

Write-Host "Reading the key from 1Password - click Allow in the app..."
$key = (& op.exe read $ref | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $key) { throw "op.exe read failed (is the app unlocked, with 'Integrate with 1Password CLI' on?)" }
Write-Host "Key read (length $($key.Length))."

$env:LLM_API_KEY = $key
$env:WSLENV = "LLM_API_KEY"   # only this variable crosses into WSL
$setup = "cd $Repo && source .venv/bin/activate && export N_CONCURRENT=$Concurrent"

if ($Mode -eq "task") {
    wsl.exe -d $Distro -- bash -c "$setup && ./scripts/run_task.sh $Arg"
    exit $LASTEXITCODE
}

$cmd = if ($Mode -eq "resume") { "./scripts/run_full.sh resume $Arg" } else { "./scripts/run_full.sh" }
# tmux so the run survives this window closing. The key goes into the session's
# environment (-e); the log gets a closing line so a dead run is obvious.
$inner = "$setup && tmux new-session -d -s full -e LLM_API_KEY=`"`$LLM_API_KEY`" -e N_CONCURRENT=$Concurrent " +
         "'cd $Repo && source .venv/bin/activate && $cmd 2>&1 | tee -a jobs/full-run.log; " +
         "echo \`"== run exited `$(date) ==\`" | tee -a jobs/full-run.log'"
wsl.exe -d $Distro -- bash -c $inner
if ($LASTEXITCODE -ne 0) { throw "could not start the tmux session. If one named 'full' is left from a dead run: wsl -d $Distro -- tmux kill-session -t full" }
Write-Host "Started in tmux session 'full'. Progress:  wsl -d $Distro -- bash -lc '$Repo/scripts/full_progress.sh'"
Write-Host "Attach:  wsl -d $Distro -- tmux attach -t full   (Ctrl-b d to leave)"
