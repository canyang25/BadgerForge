#!/usr/bin/env bash
# Script to run the LGAgent against a Terminal-Bench 2.1 task.
# This script must be run on your base system (host) where Docker is installed.

set -euo pipefail

# Ensure we're in the workspace directory (BadgerForge)
cd "$(dirname "$0")"
WORKSPACE_ROOT="$(pwd)"

# On the host, terminal-bench-2-1 is a sibling directory to BadgerForge
DATASET_PATH="${WORKSPACE_ROOT}/../terminal-bench-2-1/tasks"

# Allow overriding the task name, defaulting to cancel-async-tasks
if [[ $# -gt 0 && ! "$1" == -* ]]; then
  TASK_NAME="$1"
  shift
else
  TASK_NAME="cancel-async-tasks"
fi

if [ ! -d "$DATASET_PATH" ]; then
  echo "Error: Dataset directory not found at $DATASET_PATH."
  echo "Ensure the terminal-bench-2-1 directory exists parallel to this directory."
  exit 1
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "Warning: OPENAI_API_KEY is not set. Ensure it is set before running."
fi

echo "Evaluating task: $TASK_NAME"
# We set PYTHONPATH to the workspace root so harbor can find lg_agent.agent:LGAgent
# We pass the dataset path with -p and filter for the specific task with -i
PYTHONPATH="$WORKSPACE_ROOT" harbor run -p "$DATASET_PATH" -i "$TASK_NAME" -a lg_agent.agent:LGAgent "$@"
