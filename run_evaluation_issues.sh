#!/usr/bin/env bash
set -euo pipefail

# Resolve script directory so PYTHONPATH is always set correctly
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH=".:${PYTHONPATH:-}"

CONCURRENCY="${CONCURRENCY:-2}"
DATASET="${DATASET:-terminal-bench/terminal-bench-2-1}"
AGENT="${AGENT:-lg_agent.agent:LGAgent}"
TRIALS="${TRIALS:-1}"

# 12 failed tasks that directly test the recent architectural fixes:
TASKS=(
  "openssl-selfsigned-cert"
  "qemu-alpine-ssh"
  "pypi-server"
  "write-compressor"
  "dna-assembly"
  "torch-pipeline-parallelism"
  "torch-tensor-parallelism"
  "kv-store-grpc"
  "schemelike-metacircular-eval"
  "log-summary-date-ranges"
  "regex-chess"
  "mteb-retrieve"
)

TASK_ARGS=()
for task in "${TASKS[@]}"; do
  TASK_ARGS+=(-i "$task")
done

echo "=== Running Targeted Issue Evaluation (12 Tasks) ==="
echo "Dataset: $DATASET | Concurrency: $CONCURRENCY | Trials: $TRIALS"
echo "Tasks to evaluate:"
printf '  - %s\n' "${TASKS[@]}"

harbor run \
  -d "$DATASET" \
  -a "$AGENT" \
  -n "$CONCURRENCY" \
  -k "$TRIALS" \
  "${TASK_ARGS[@]}" \
  "$@"