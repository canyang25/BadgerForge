#!/usr/bin/env bash
# Run every Terminal-Bench 2.1 task once: our full score, and the sweep the
# next dev slice is picked from. Expect 8-12 hours.
#
#   ./scripts/run_full.sh                            start a new job
#   ./scripts/run_full.sh resume <job dir>           continue an interrupted one
#   ./scripts/run_full.sh subset <job dir> <task>... some tasks, N_TRIALS each (default 1)
#
# Resuming skips trials that finished, re-runs unfinished ones (a trial
# directory with no result.json) and the ones that failed on the gateway
# connection or on authentication, so a dropped VPN costs a restart, not the
# night. To redo a trial that finished, delete its directory first.
#
# Env: TB_TASKS (task dir), N_CONCURRENT (default 3; use 2 if WSL has under
# 24 GB, since eight tasks ask for 8 GB each). On Windows start this through
# scripts/run_full_windows.ps1, which supplies LLM_API_KEY (docs/setup-windows.md).
set -euo pipefail
cd "$(dirname "$0")/.."

TB_TASKS="${TB_TASKS:-$HOME/terminal-bench-2-1/tasks}"
N="${N_CONCURRENT:-3}"

source scripts/env.sh

if [ "${1:-}" = "resume" ]; then
  DIR="${2:?usage: run_full.sh resume <job dir>}"
  # harbor puts config.json one level down (jobs/full-<ts>/<job id>/). No
  # `ls ... | head` here: with pipefail, ls failing on the missing top-level
  # path made the whole script exit silently before anything resumed.
  CFG=""
  for f in "$DIR"/config.json "$DIR"/*/config.json; do
    [ -f "$f" ] && { CFG="$f"; break; }
  done
  [ -n "$CFG" ] || { echo "No config.json under $DIR" >&2; exit 1; }
  echo "Resuming $(dirname "$CFG")"
  exec harbor jobs resume -p "$(dirname "$CFG")" \
    -f APIConnectionError -f APITimeoutError -f AuthenticationError
fi

[ -d "$TB_TASKS" ] || { echo "No task dir at $TB_TASKS (set TB_TASKS)" >&2; exit 1; }

if [ "${1:-}" = "subset" ]; then
  # A slice: the named tasks only, N_TRIALS attempts each, into the given job
  # dir. Same agent, same dataset dir; harbor filters by -i.
  JOB="${2:?usage: run_full.sh subset <job dir> <task>...}"
  shift 2
  [ $# -gt 0 ] || { echo "subset: name at least one task" >&2; exit 1; }
  INCLUDE=()
  for t in "$@"; do
    [ -d "$TB_TASKS/$t" ] || { echo "No such task: $TB_TASKS/$t" >&2; exit 1; }
    INCLUDE+=(-i "$t")
  done
  K="${N_TRIALS:-1}"
  echo "Job: $JOB   tasks: $#   trials each: $K   concurrency: $N"
  exec harbor run -p "$TB_TASKS" "${INCLUDE[@]}" --agent agent.agent:BaselineAgent -k "$K" -n "$N" -o "$JOB"
fi

JOB="jobs/full-$(date +%Y%m%d-%H%M)"
echo "Job: $JOB   concurrency: $N"
echo "If it stops, run:  ./scripts/run_full.sh resume $JOB"
exec harbor run -p "$TB_TASKS" --agent agent.agent:BaselineAgent -k 1 -n "$N" -o "$JOB"
