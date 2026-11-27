#!/usr/bin/env bash
set -euo pipefail

# Resolve script directory so PYTHONPATH is always set correctly
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH=".:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

CONCURRENCY="${CONCURRENCY:-2}"
DATASET="${DATASET:-terminal-bench/terminal-bench-2-1}"
AGENT="${AGENT:-lg_agent.agent:LGAgent}"
TRIALS="${TRIALS:-1}"

# 4 failed tasks that directly test the recent prompt improvements
# (apt-get backgrounding, sed peek-hole reading, and over-engineering analysis scripts)
TASKS=(
  "terminal-bench/caffe-cifar-10"
  "terminal-bench/code-from-image"
  "terminal-bench/gcode-to-text"
  "terminal-bench/dna-assembly"
)

TASK_ARGS=()
for task in "${TASKS[@]}"; do
  TASK_ARGS+=(-i "$task")
done

echo "=== Running Targeted Issue Evaluation (4 Tasks) ==="
echo "Dataset: $DATASET | Concurrency: $CONCURRENCY | Trials: $TRIALS"
echo "Tasks to evaluate:"
printf '  - %s\n' "${TASKS[@]}"

harbor run \
  -d "$DATASET" \
  -a "$AGENT" \
  -n "$CONCURRENCY" \
  -k "$TRIALS" \
  --yes \
  ${TASK_ARGS[@]+"${TASK_ARGS[@]}"} \
  ${@+"$@"}