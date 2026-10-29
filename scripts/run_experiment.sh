#!/usr/bin/env bash
# Load gateway settings once; Python applies the experiment flags afterward.
set -euo pipefail
cd "$(dirname "$0")/.."
_bf_preview=0
for _bf_arg in "$@"; do
  case "$_bf_arg" in --dry-run|-h|--help) _bf_preview=1;; esac
done
if [ "$_bf_preview" = 0 ] && [ "$#" -gt 0 ]; then
  source scripts/env.sh
fi
exec "${BF_PYTHON:-python3}" scripts/run_experiment.py "$@"
