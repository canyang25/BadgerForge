#!/usr/bin/env bash
# Run every Terminal-Bench 2.1 task once: our full score, and the sweep the
# next dev slice is picked from. Expect 8-12 hours.
#
#   ./scripts/run_full.sh                  start a new job
#   ./scripts/run_full.sh resume <job dir> continue an interrupted one
#
# Resuming skips trials that finished and re-runs the ones that failed on the
# gateway connection, so a dropped VPN costs a restart, not the night.
#
# Env: TB_TASKS (task dir), N_CONCURRENT (default 3; use 2 if WSL has under
# 24 GB, since eight tasks ask for 8 GB each).
set -euo pipefail
cd "$(dirname "$0")/.."

TB_TASKS="${TB_TASKS:-$HOME/terminal-bench-2-1/tasks}"
N="${N_CONCURRENT:-3}"

source scripts/env.sh

if [ "${1:-}" = "resume" ]; then
  DIR="${2:?usage: run_full.sh resume <job dir>}"
  CFG="$(ls "$DIR"/config.json "$DIR"/*/config.json 2>/dev/null | head -n 1)"
  [ -n "$CFG" ] || { echo "No config.json under $DIR" >&2; exit 1; }
  echo "Resuming $(dirname "$CFG")"
  exec harbor jobs resume -p "$(dirname "$CFG")" -f APIConnectionError -f APITimeoutError
fi

[ -d "$TB_TASKS" ] || { echo "No task dir at $TB_TASKS (set TB_TASKS)" >&2; exit 1; }
JOB="jobs/full-$(date +%Y%m%d-%H%M)"
echo "Job: $JOB   concurrency: $N"
echo "If it stops, run:  ./scripts/run_full.sh resume $JOB"
exec harbor run -p "$TB_TASKS" --agent agent.agent:BaselineAgent -k 1 -n "$N" -o "$JOB"
