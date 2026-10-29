# Evaluating the LangGraph branch

Merge the readiness PRs into `preston-test` before collecting graph results:
[sync main](https://github.com/canyang25/BadgerForge/pull/41),
[preserve shaped diagnostics](https://github.com/canyang25/BadgerForge/pull/42),
and [retain context during cancellation](https://github.com/canyang25/BadgerForge/pull/43).
The progress trace change records which trigger fired without changing its
prompt or routing. Both optional nodes stay off by default.

## Local correctness

Install the existing declared dependencies and run the suite:

```bash
uv pip install -e ".[dev]"
python -m pytest -q
```

The suite covers routing and stopping behavior, cancellation during model
requests and command execution, and shaping mixed numeric/binary output
without losing readable diagnostics. Check the built wheel includes all
`agent/prompts/*.md` files when changing packaging.

## Controlled benchmark runs

Use the x86 Windows/WSL2 environment described in `docs/setup-windows.md`,
with Docker running and gateway access configured through `.env.op.local`.
Set `TB_TASKS` to the Terminal-Bench task directory on that machine. Keep
agent experiment flags out of `.env.op.local`; the commands below set them
for each run. Finish each job before switching the checkout.

Keep the model, reasoning effort, output limit, temperature, command timeout,
task time limits, and concurrency identical across arms. Record each exact
commit (`git rev-parse HEAD`), flag values, and job directory. Each arm uses
three attempts per task. Start with this existing dev slice in Bash:

```bash
TASKS=(
  compile-compcert extract-elf feal-linear-cryptanalysis largest-eigenval
  modernize-scientific-stack portfolio-optimization regex-log
  reshard-c4-data sqlite-db-truncate write-compressor
)
export N_TRIALS=3 N_CONCURRENT=2 AGENT_COMMAND_TIMEOUT_SEC=60
```

First run the existing loop from the current `main` commit. Then run the
updated graph commit with the same settings and both experiments off. Use
different job directories for the two commits:

```bash
# Existing loop checkout:
AGENT_MAX_TURNS=100 AGENT_PROGRESS_CHECK=0 AGENT_OBSERVATION_SHAPE=0 \
  ./scripts/run_full.sh subset jobs/loop-control "${TASKS[@]}"

# Updated graph checkout:
AGENT_MAX_TURNS=100 AGENT_PROGRESS_CHECK=0 AGENT_OBSERVATION_SHAPE=0 \
  ./scripts/run_full.sh subset jobs/graph-control "${TASKS[@]}"
```

Inspect discrepancies in pass rates, stops, commands, and token/time costs
before adding behavior. Graph parity requires benchmark evidence as well as
the unit suite. Once established, compare each following arm separately
against a graph control run under comparable gateway conditions:

```bash
# Progress only:
AGENT_MAX_TURNS=100 AGENT_PROGRESS_CHECK=1 AGENT_PROGRESS_EVERY=10 \
  AGENT_OBSERVATION_SHAPE=0 \
  ./scripts/run_full.sh subset jobs/graph-progress "${TASKS[@]}"

# Higher turn cap only; task time limits remain unchanged:
AGENT_MAX_TURNS=150 AGENT_PROGRESS_CHECK=0 AGENT_OBSERVATION_SHAPE=0 \
  ./scripts/run_full.sh subset jobs/graph-turns150 "${TASKS[@]}"

# Shaping only, after the diagnostics fix:
AGENT_MAX_TURNS=100 AGENT_PROGRESS_CHECK=0 AGENT_OBSERVATION_SHAPE=1 \
  ./scripts/run_full.sh subset jobs/graph-shaping "${TASKS[@]}"
```

Use fresh job directories for repeated comparisons. Alternate control and
variant batches when possible to reduce time-of-day gateway effects. Keep
infrastructure failures visible and rerun interrupted/failed infrastructure
trials using the documented resume procedure. Report the unfiltered score
and, for diagnosis, the version excluding infrastructure failures.

Harbor places trial results inside the actual job directory, which can be
one level below the requested output directory. Pass that directory to
`python scripts/score.py <job-dir>` and use
`python scripts/export_trials.py <output-dir> --out <summary.csv>` for
trial-level passes, outcomes, tokens, and seconds.

## Verify the experiment actually acts

Progress rows in `agent_result.metadata.node_trace` now include:

- `reasons`: `periodic`, `identical_failures`, or both;
- `turn`: the turn after which the check was inserted;
- `progress_every` and `identical_failures`: the trigger settings/state.

A fired check establishes activation. Inspect the following commands and
observations to determine whether the agent changed approach or repeated the
same idea. Record activation counts, strategy changes, extra turns/tokens,
and eventual outcomes. For shaping, inspect `shape` rows and the retained
messages to confirm useful errors survived and the next action uses them.
For the turn cap, identify which trials reach 100 turns with time remaining.

The current slice can miss targeted failures. Select any additional stuck
tasks from saved transcripts before running, then use the same expanded set
for control and variant. The checked-in analysis names five stuck-approach
tasks as a group; it does not identify all five individually.

Small differences across 30 trials need confirmation; prior full runs of the
same agent varied by about four solved tasks. Validate a promising single
change on all 89 tasks before combining features or changing defaults.
