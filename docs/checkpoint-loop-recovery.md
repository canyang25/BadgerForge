# Checkpoint and loop recovery on `preston-test`

## Goal

Recover benchmark passes on tasks where the agent spends its budget without
writing a usable answer or spends several turns on a failing approach. Test
the early-deliverable checkpoint first. Use saved trajectories to choose one
loop recovery trigger for the second PR.

## PR 1 — Early-deliverable pilot

The `deliverable` profile adds a one-time instruction after the first executed
command on or after turn five. It asks the agent to save a
plausible artifact and then refine it. The first smoke test passed all six
trials in each arm. In the full LangGraph run, `llm-inference-batching-scheduler`
spent 40 turns and timed out before writing its plans. [Smoke test](experiments.md#2026-10-29--early-deliverable-checkpoint-two-task-live-smoke)
· [Full graph run](https://github.com/canyang25/BadgerForge/blob/09b9d813f8c5fe3a47f33de8bec9337cd1a3fb2c/docs/experiments.md#L28-L34)

| Task | What to look for |
|---|---|
| `llm-inference-batching-scheduler` | The first candidate plan for each input bucket |
| `protein-assembly` | The first sequence written to `/app/gblock.txt` |
| `regex-log` | A passing control for regressions |

Use one clean `preston-test` commit, the same Docker host and Qwen settings,
and Terminal-Bench 2.1 at `7131e4375048a0e408a8fb404b5f499d726b695b`. Run three
rounds with one trial per task in each arm. Reverse arm order in round two.
The scheduler and protein tasks each have a 30-minute agent limit.
Use a fresh job prefix for each pilot. Add `--dry-run` to preview settings and
the dataset pin. [Launcher instructions](langgraph-evaluation.md#controlled-benchmark-runs)

```bash
set -e
tasks=(llm-inference-batching-scheduler protein-assembly regex-log)
pilot=jobs/checkpoint-pilot
for round in 1 2 3; do
  profiles=(control deliverable)
  if (( round == 2 )); then profiles=(deliverable control); fi
  for profile in "${profiles[@]}"; do
    bash scripts/run_experiment.sh "$profile" "$pilot-r${round}-${profile}" \
      "${tasks[@]}" --trials 1 --concurrency 2
  done
done
```

Record Harbor reward, timeouts, tokens, and the turn when the checkpoint
appears. Read `agent_result.metadata.node_trace` for activation and match the
shell commands in `agent_result.metadata.messages` to their observations.
Record the first observed write to the required path. Use the final Harbor
result to judge whether the run produced a passing submission. Expand the
pilot if the checkpoint gets a usable artifact written earlier on a failing
task and the extra passes recur while the passing control holds up.

## PR 2 — Loop recovery

Replay the detector on existing failed and passing transcripts. The six local
`protein-assembly` trials contain no exact A–B–A–B command cycles. Some failures
show repeated HTTP access denials from one site even though the commands vary.
Use three consecutive observations that report HTTP 403 from one named site.
Use the literal URLs in the command to identify the site. An observation with
another HTTP status or a command that names several sites breaks the streak.

Use the existing execution observation and loop guard for a single recovery
message when the trigger fires. Include the observed failure and ask the model
to change its approach on the next normal turn. Limit any command refusal to
one retry of the same failed command. Put the behavior behind its own
`loop-recovery` experiment profile. Keep the checkpoint disabled in that
comparison. The execute and guard trace rows record the recovery action and
site when the hint or refusal fires. [Loop recovery PR](https://github.com/canyang25/BadgerForge/pull/58)

Test the trigger, a changed command, recovery after a successful attempt, and
the disabled profile. In the live comparison, count triggers, inspect the next
command for a genuine change of approach, and compare pass counts, timeouts, and
tokens with `control` on the same tasks.

## Follow-up

A separate completion verifier is a follow-up experiment. Its first test should
exercise an explicit deliverable requirement and return the observed mismatch
to the agent for a bounded repair.
