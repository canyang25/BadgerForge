#!/usr/bin/env bash
# Run the baseline agent against the 10-task Terminal-Bench 2.0 sample set,
# or a single task from it:
#
#   ./scripts/run_baseline.sh                  # all 10 sample tasks
#   ./scripts/run_baseline.sh regex-log # just one task
#
# Extra harbor flags pass through, e.g.:
#   ./scripts/run_baseline.sh regex-log -m ollama/qwen2.5-coder:32b
set -euo pipefail
cd "$(dirname "$0")/.."

TASK="${1:-}"
[ $# -gt 0 ] && shift

harbor run \
  -d terminal-bench-sample@2.0 \
  --agent-import-path agent.agent:BaselineAgent \
  ${TASK:+-i "$TASK"} \
  -n "${N_CONCURRENT:-1}" \
  "$@"
