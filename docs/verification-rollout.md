# Completion verification and full-run checkpoints

## Where we are

Start from `preston-test` at `e2eba49`. Both experiment PRs are merged and
pulled. The local suite passed 180 tests and both PRs passed CI.

| Work | What we measured |
| --- | --- |
| Early deliverable | 8/9 in both arms. The scheduler wrote its plans earlier in all three enabled runs. [PR #57](https://github.com/canyang25/BadgerForge/pull/57) |
| HTTP 403 loop recovery | 2/2 control and 1/2 enabled. The hint fired once and the next command still contacted the same site. [PR #58](https://github.com/canyang25/BadgerForge/pull/58) |

Use `control` as the starting profile. These two opt-in experiments cover
three distinct tasks across 22 live trials. All three completion-verification
PRs below are planned. The older x86 graph control scored
46/89 on `d3afe4d`, with shorter effective deadlines caused by WSL clock drift.
Use a fresh matched control for the first full comparison. [Earlier x86 run](https://github.com/canyang25/BadgerForge/blob/09b9d813f8c5fe3a47f33de8bec9337cd1a3fb2c/docs/experiments.md#L6-L44)

## What merges and what gets pulled

Create each task branch from the latest `origin/preston-test`. Put the code,
tests, and pilot evidence for that task in one PR. List the prerequisite PRs
and the experiment flag in the description. After review and green checks,
squash-merge into `preston-test`. Fast-forward the integration checkout with
`git pull --ff-only origin preston-test` before branching for the next dependent
task. Use a separate clean checkout pinned to the chosen merge SHA for jobs.

Use Terminal-Bench 2.1 at `7131e4375048a0e408a8fb404b5f499d726b695b` for the task
inputs and the benchmark grader. Keep the first control and verifier profiles
at the same 100-turn cap. Evaluate a cap change in its own comparison. A later
promotion PR can select the proven integration commits and their prerequisites.
Test the candidate against the intended `main` baseline on matched settings
before using it as the submission configuration. [Turn-cap PR](https://github.com/canyang25/BadgerForge/pull/56) · [Promotion guide](promoting-changes.md)

## Batch 1 — Check completion and repair once

| PR | Implement | Checkpoint before the next task |
| --- | --- | --- |
| 1. Executable probe runner | Run one short check against selected task files in a disposable Docker container. Use read-only copies of the candidate files and a writable scratch directory. Start with `cancel-async-tasks`. Interrupt a runner after a worker begins and check that its cleanup handler ran. | Known-good and known-bad fixtures yield the expected verdict. A timed-out probe returns inconclusive and cleans up. The candidate files pass a before-and-after hash check. |
| 2. Shadow completion | Add `verify-shadow` on the first parsed `TASK_COMPLETE`. Use one fresh Qwen request with the original instruction and relevant artifact paths to select an explicit requirement and generate a check. Record the verdict, evidence, elapsed time, tokens, and skips. Submit the candidate for Harbor grading. | Check executable behavior on `cancel-async-tasks` and `query-optimize`, with `regex-log` as a passing control. Compare shadow verdicts with Harbor grades and inspect any passing candidate that the probe would have rejected. |
| 3. One bounded repair | Add `verify`. A demonstrated violation gives the agent the expected and observed results and one ordinary repair turn. A passing, inconclusive, or skipped probe routes to submission. Grade the workspace after the repair command or a renewed completion claim. | Run the same targeted tasks with `control` and `verify`, three attempts per task per arm. Record whether the check fired, whether the agent repaired the requirement, and the final Harbor reward. |

Use the `cancel-async-tasks` fixture to validate execution. The node in PR 2
takes its requirements and allowed inputs from task instructions. For the SQL
pilot, run the candidate query and supplied baseline against SQLite read-only
and compare their outputs. Harbor grades each task through its regular path.

At the first completion claim, checkpoint the selected candidate paths and
hashes that went into the probe. Keep the copy and diagnostic with the trial
logs. Pass the effective per-task time limit from Harbor's launch settings
into the agent, and measure remaining time from the start of `run()`. Start
with 120 seconds of remaining budget before entering the verifier, with up to
45 seconds for the whole probe and up to 60 seconds for repair. That leaves
15 seconds for submission. Apply the same trial deadline in both arms.

**Run full checkpoint 1 after PRs 1–3 merge and the targeted pilot finishes.**
Exercise the repair path on a known-bad fixture before the pilot. Freeze the
merged SHA and run `control` and `verify` on all 89 tasks. The pilot shows
which failures the probe can reach on the slice. The full pair measures the
effect across the benchmark.

## Batch 2 — Manage the deadline

| PR | Implement | Checkpoint before the next task |
| --- | --- | --- |
| 4. Timing trace | Record time spent in model calls and shell commands, time remaining near cutoff, and the first observed candidate write. Reuse the deadline data from Batch 1. | Replay timeout cases and verify the trace identifies what took time and whether a candidate existed before the deadline. |
| 5. Deadline-aware checkpoint | Use the timing evidence to place one early-deliverable prompt when a trial is running low on time and a required output file is still missing. Reuse the existing prompt and next normal model turn. | Compare the new trigger on the scheduler and protein tasks, with `regex-log` as a passing control. Record time to the first write and final passes. |

**Run full checkpoint 2 after PRs 4–5 merge and their targeted pilot.** Use the
profile selected at checkpoint 1 for the control, then enable the deadline
checkpoint in the candidate profile. Save named launcher profiles for the two
arms. Use the same pattern after every later batch of two or three related PRs
that introduces a runnable behavior change. Each full comparison tests one
named change or one named group of changes.

## What to save at each checkpoint

- **After each PR** record its merge SHA, dependencies, profile, unit and CI
  results, pilot job IDs, and the next PR in the sequence. Update the
  [experiment log](experiments.md) when evidence is collected.
- **Before a full comparison** freeze one clean x86 checkout, the dataset
  SHA, model settings, per-task limits, and concurrency. Save both dry-run
  manifests and check the intended profile difference. On WSL, check the
  clock against the Windows host so differences in effective budgets are
  visible. Use the same measured setup for both arms.
- **After a full comparison** verify one finalized grader result for each of
  the 89 tasks in each arm. Save the manifests and raw trials under `jobs/`.
  Record per-task rewards, timeouts, verifier activations, tokens, and runtime.
  Publish compact trial summaries under `eval/results/` and link the run in
  the experiment log. Use the recorded profile and commit when resuming an
  interrupted arm. [Run and resume guide](setup-windows.md)

## Running the full checkpoint

Use the x86 runner with gateway credentials already configured. Export
`TB_TASKS` before running. The `verify` profile becomes available after PR 3.
Use a new job prefix for each comparison. To preview the manifests, add
`--dry-run` to each launcher command.

```bash
set -euo pipefail
: "${TB_TASKS:?Set TB_TASKS to the pinned Terminal-Bench tasks directory}"
tasks=()
for task_dir in "$TB_TASKS"/*; do
  if [[ -f "$task_dir/task.toml" ]]; then tasks+=("${task_dir##*/}"); fi
done
if (( ${#tasks[@]} != 89 )); then
  printf 'Expected 89 tasks, found %s\n' "${#tasks[@]}" >&2
  exit 1
fi

bash scripts/run_experiment.sh control jobs/full-verification-control \
  "${tasks[@]}" --trials 1 --concurrency 2
bash scripts/run_experiment.sh verify jobs/full-verification-candidate \
  "${tasks[@]}" --trials 1 --concurrency 2
```

One full pair is 178 trials. The earlier x86 control took 6 h 50 min for one
arm at concurrency two. Run the arms back-to-back and record gateway speed.
Use the scoring and export scripts to check both arms. Compare passes gained
and lost on matching tasks, then review where the verifier fired or added
cost. Keep infrastructure failures visible and record reruns. A change of
only a few passes is within the spread seen across earlier full runs. Repeat
a close comparison in reverse arm order under matched settings before using
it to change the default profile. [Scoring and export](langgraph-evaluation.md#controlled-benchmark-runs) · [Full-run history](https://github.com/canyang25/BadgerForge/blob/09b9d813f8c5fe3a47f33de8bec9337cd1a3fb2c/docs/experiments.md#L125-L129)
