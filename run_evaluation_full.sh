#!/usr/bin/env bash
set -euo pipefail

# Resolve script directory so PYTHONPATH is always set correctly
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH=".:${PYTHONPATH:-}"

# Concurrency defaults to 2 for overnight reliability; can be overridden via CONCURRENCY=4
CONCURRENCY="${CONCURRENCY:-2}"
DATASET="${DATASET:-terminal-bench/terminal-bench-2-1}"
AGENT="${AGENT:-lg_agent.agent:LGAgent}"
TRIALS="${TRIALS:-1}"

echo "=== Running Full Benchmark ==="
echo "Dataset: $DATASET | Concurrency: $CONCURRENCY | Trials: $TRIALS"
harbor run \
  -d "$DATASET" \
  -a "$AGENT" \
  -n "$CONCURRENCY" \
  -k "$TRIALS" \
  "$@"