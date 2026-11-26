#!/usr/bin/env bash
set -euo pipefail

# Resolve script directory so PYTHONPATH is always set correctly
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH=".:${PYTHONPATH:-}"

# Default to 2 concurrent containers; can be overridden via CONCURRENCY=4 ./run_evaluation_sample.sh
CONCURRENCY="${CONCURRENCY:-2}"
DATASET="${DATASET:-terminal-bench-sample@2.0}"
AGENT="${AGENT:-lg_agent.agent:LGAgent}"

echo "=== Running Sample Benchmark (10 tasks) ==="
echo "Dataset: $DATASET | Concurrency: $CONCURRENCY"
harbor run \
  -d "$DATASET" \
  -a "$AGENT" \
  -n "$CONCURRENCY" \
  "$@"