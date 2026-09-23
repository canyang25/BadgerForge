#!/usr/bin/env bash
# Run our agent on one Terminal-Bench 2.1 task.
#
#   ./scripts/run_task.sh regex-log
#
# Requires: Docker running, GlobalProtect VPN, 1Password CLI signed in,
# and TB_TASKS pointing at a clone of harbor-framework/terminal-bench-2-1.
set -euo pipefail
cd "$(dirname "$0")/.."

TASK="${1:?usage: run_task.sh <task-name> [extra harbor flags]}"
shift
TB_TASKS="${TB_TASKS:-$HOME/Documents/terminal-bench-2-1/tasks}"

[ -d "$TB_TASKS/$TASK" ] || { echo "No such task: $TB_TASKS/$TASK" >&2; exit 1; }

op run --env-file=.env.op -- \
  harbor run -p "$TB_TASKS/$TASK" --agent agent.agent:BaselineAgent "$@"
