# BadgerForge LangGraph Agent (`lg_agent`)

This directory contains our LangGraph-based, Harbor-compatible AI coding agent for the MLM26 Efficient Coder Challenge. The agent uses a multi-worker architecture to solve complex terminal-based software engineering tasks.

## Architecture Overview

The agent is driven by a LangGraph state machine located in `graph.py`. It consists of a Supervisor node that orchestrates several specialized worker nodes:
* **Supervisor**: Plans, delegates tasks, and decides when a task is finished.
* **Researcher**: Explores the file system and reads files (read-only).
* **Coder**: Handles standard code implementation and file modifications.
* **MediumCoder**: Handles complex implementations and first-time test failures.
* **ExpertCoder**: Handles persistent bugs and deep algorithmic problem-solving.
* **Tester**: Executes test commands in the container and reports the results back to the Supervisor.

### Key Files
* `agent.py`: The Harbor `BaseAgent` wrapper. Handles the execution loop, token tracking, trajectory serialization, and hard time/turn limits.
* `graph.py`: The core LangGraph definition, containing the state schema, tools, prompts, LLM clients, and routing logic.
* `models.py`: Data models and tracking metadata (e.g., `RunMetadata`).
* `observability.py`: Functions for logging runs.

## Assumed Directory Structure

For the local evaluation scripts (specifically `run_evaluation.sh`) to work correctly, your workspace should have the following sibling directory structure:

```text
Projects/
├── BadgerForge/               # This repository (run scripts from here)
│   ├── lg_agent/              # Agent code
│   ├── run_evaluation.sh      # Eval scripts
│   └── ...
└── terminal-bench-2-1/        # Local clone of the dataset
    └── tasks/                 # Task definitions
```
*(Note: `run_evaluation_issues.sh`, `run_evaluation_sample.sh`, and `run_evaluation_full.sh` pull tasks directly via Harbor, but they should still be run from the `BadgerForge` root directory).*

## Running the Agent

To run the agent against Terminal-Bench tasks, you can use Harbor directly or one of our dedicated evaluation scripts.

### Evaluation Scripts
We have multiple scripts in the root directory to evaluate the agent depending on your current goal:

* **`./run_evaluation_sample.sh`**: Runs the agent against the `terminal-bench-sample@2.0` dataset (10 tasks). Great for a quick baseline check.
* **`./run_evaluation_issues.sh`**: Runs a targeted set of tasks to debug specific failures. To modify the selected tasks, open this script and edit the `TASKS=(...)` array to include the exact Harbor task IDs you want to evaluate.
* **`./run_evaluation.sh <task-name>`**: Runs a single task locally. It expects the `terminal-bench-2-1` dataset to be cloned locally in a sibling directory (see *Assumed Directory Structure*). Defaults to `cancel-async-tasks` if no argument is provided.
* **`./run_evaluation_full.sh`**: Runs the complete `terminal-bench/terminal-bench-2-1` dataset. Configured for a safe concurrency of 2 by default, which is ideal for overnight runs.

**Using Harbor directly:**
```bash
harbor run -d terminal-bench/terminal-bench-2-1 -a lg_agent.agent:LGAgent -i terminal-bench/caffe-cifar-10
```

## Testing & Debugging

1. **Check the Trajectory Logs**: When a run finishes, Harbor saves the results in the `jobs/` directory. You can view them using `harbor view jobs`. Additionally, our custom logging writes markdown trajectory reports to `.okf/runs/`. Check these to see the exact conversation history, tool calls, and execution environment outputs.
2. **Unit Tests**: Place any non-Docker/non-LLM unit tests in the top-level `tests/` directory (as per `CONTRIBUTING.md`). 
3. **Debugging Timeouts/Infinite Loops**: If the agent gets stuck in a loop, `agent.py` enforces a `MAX_WALL_CLOCK_SEC` (default 840s) and `MAX_TURNS` (default 150) limit to prevent runaway costs. `graph.py` also features an automatic loop-breaking nudge if it detects a worker endlessly exploring without taking action.

## Modifying the Agent

Before making changes, remember to follow the rules in `CONTRIBUTING.md` (claim files, keep PRs under ~400 lines, etc.). 

### Modifying Prompts
Prompts for all nodes are located at the bottom of `graph.py`. If you want to change how a specific worker behaves, adjust their system prompt. **Tip:** We use strong directive language (e.g., "TIME LIMIT", "CRITICAL", "Do NOT") to keep the LLMs aligned.

### Adding or Modifying Tools
Tools are defined as Pydantic classes inside `create_agent_graph()` in `graph.py`. 
1. Define the Pydantic model (e.g., `class AppendToFile(BaseModel): ...`).
2. Update the `execute_tools()` function to handle the new tool execution within the container environment.
3. Add the tool to the specific node's tool list when calling `create_agent_node(..., tools=[...])`.
4. Update the respective node's prompt to instruct it on when and how to use the new tool.

### Changing Routing Logic
The `router()` function in `graph.py` dictates the flow of the state machine. By default:
- AI messages are routed to the `tools` node.
- Tool execution results route back to the sender (unless the tool was `Delegate` or `ReportBack`, which explicitly sets the `next_agent` state).
- Explicit nudges and warnings automatically route back to the sender to force them to correct their behavior.

### LLM Client Configuration
We use `ChatOpenAI` mapped to `qwen3.8-27b` via the DOIT gateway. If you need to tweak temperatures, timeouts, or fallback models, modify the client instantiations at the top of `create_agent_graph()` in `graph.py`.
