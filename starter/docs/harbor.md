# Harbor orientation

[Harbor](https://www.harborframework.com/docs) is the official evaluation framework for Terminal-Bench 2.0, from the creators of Terminal-Bench. It handles everything that isn't your agent: pulling task definitions, building and destroying Docker containers, enforcing timeouts, running the verifier, and aggregating scores.

The containers aren't just plumbing — they're your safety layer. You're building an agent that runs arbitrary shell commands, and inside `harbor run` every one of those commands executes in a disposable container with no access to your real filesystem: whatever the agent breaks gets destroyed with the container. That protection only exists inside Harbor, so test your agent through it rather than against a local shell — see [safety.md](safety.md).

## The mental model

```
harbor run
   │
   ├─ for each task in the dataset:
   │     1. build the task's Docker container        (environment setup)
   │     2. call your agent's setup(environment)     (agent setup)
   │     3. call your agent's run(instruction, ...)  (agent execution)
   │     4. run the task's tests/test.sh             (verifier → reward)
   │     5. destroy the container
   │
   └─ write results to ./jobs/<job-name>/
```

Your agent never touches your filesystem — it acts on the container through `environment.exec(...)`. The verifier grades the **final container state**, not what your agent said.

## Datasets you'll use

| Dataset | Tasks | Use |
|---|---|---|
| `terminal-bench-sample@2.0` | 10 | Setup verification, quick iteration |
| `terminal-bench@2.0` | 89 | The real benchmark; the challenge public subset is drawn from it |
| `terminal-bench-pro@1.0` | 200 | Extended public set — extra practice tasks, not used for scoring |

List everything with `harbor datasets list`.

## Commands you'll actually run

```bash
# Sanity-check your setup (no model needed — oracle replays known solutions)
harbor run -d terminal-bench-sample@2.0 -a oracle

# Run your agent on one task
harbor run -d terminal-bench-sample@2.0 \
  --agent agent.agent:BaselineAgent -i regex-log

# Run the public subset (what you self-report)
./scripts/run_subset.sh

# Useful flags
#   -i / --include-task-name   include tasks (repeatable, globs ok)
#   -x / --exclude-task-name   exclude tasks
#   -n / --n-concurrent        parallel containers (watch your RAM)
#   -m / --model               records model info in results
#   --n-attempts               attempts per task (this challenge scores single-attempt; the public Terminal-Bench leaderboard requires 5)
#   --jobs-dir                 output directory (default ./jobs)
```

## Reading your results

Each run writes `./jobs/<job-name>/` containing per-trial directories with a `result.json` (reward score, timing for each phase, exception info if the trial crashed). The console prints the aggregate score at the end. When you self-report a score, include the job directory name and the command you ran — that's what makes it verifiable later.

## Writing your own agent

The baseline (`agent/agent.py`) is an **external agent**: it subclasses `harbor.agents.base.BaseAgent` and drives the container from outside via `environment.exec(command=..., timeout_sec=...)`, which returns an `ExecResult` with `stdout`, `stderr`, and `return_code`.

You must implement:

- `name()` — static, the agent's identifier
- `version()` — version string
- `setup(environment)` — async; install anything your agent needs in the container (the baseline needs nothing)
- `run(instruction, environment, context)` — async; do the work. Populate `context` (token counts, metadata) **as you go**, so a timeout still reports partial usage.

The alternative is an **installed agent** (`BaseInstalledAgent`): your agent gets installed *into* the container and runs headless inside it. More moving parts, but it can bring its own tools. Consider it once your external agent plateaus.

Run any custom agent with:

```bash
harbor run -d <dataset@version> --agent your.module:YourAgentClass
```

Note: Harbor imports your agent class with a plain Python import, so your agent package must be installed in the same virtual environment as `harbor` — that's why setup uses `uv pip install -e starter/` (from the repo root) rather than a plain requirements file.

## Submitting to the public Terminal-Bench leaderboard

Optional but encouraged — it's a real leaderboard the field watches.

1. Run with 5 attempts: `harbor run -d terminal-bench@2.0 --agent ... --n-attempts 5 --jobs-dir ./my-submission`
2. Fork the [terminal-bench-2-leaderboard](https://huggingface.co/datasets/harborframework/terminal-bench-2-leaderboard) HuggingFace dataset repo
3. Add your jobs + a `metadata.yaml` under `submissions/terminal-bench/2.0/<agent>__<model>/` per the repo README
4. Open a PR — a validation bot checks it (≥5 trials per task, `timeout_multiplier` 1.0, valid result files), then a maintainer merges

View the leaderboard at [tbench.ai/leaderboard](https://www.tbench.ai/leaderboard).
