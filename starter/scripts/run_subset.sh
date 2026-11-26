#!/usr/bin/env bash
# Run your agent against the official public subset (eval/public_subset.txt).
# This is the score you post in the Kaggle Discussion tab.
#
#   ./scripts/run_subset.sh
#   ./scripts/run_subset.sh -m ollama/qwen2.5-coder:32b   # extra flags pass through
set -euo pipefail
cd "$(dirname "$0")/.."

SUBSET_FILE="eval/public_subset.txt"

include_flags=()
while IFS= read -r line; do
  line="${line%%#*}"
  line="$(echo "$line" | xargs)"   # trim whitespace
  [ -n "$line" ] && include_flags+=(-i "$line")
done < "$SUBSET_FILE"

if [ ${#include_flags[@]} -eq 0 ]; then
  echo "error: no task names found in $SUBSET_FILE" >&2
  exit 1
fi

harbor run \
  -d terminal-bench@2.0 \
  --agent-import-path agent.agent:BaselineAgent \
  "${include_flags[@]}" \
  -n "${N_CONCURRENT:-2}" \
  "$@"
