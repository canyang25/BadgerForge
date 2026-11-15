# Research plan for agent changes

Choose the next experiment using the published work and BadgerForge's own
traces. Start with the current `preston-test` control. A completion check,
deadline handling, loop recovery, and task decomposition are candidates. The
research checkpoint should recommend the smallest change with a credible way
to improve passes, or recommend the current control.

## What we know so far

| Evidence | What it suggests investigating |
| --- | --- |
| The earlier audit counted 56 confidently wrong answers among 85 failures on sometimes-solved tasks. In 53 of those 56 cases the agent checked something that missed a task requirement. The later checklist passed 20/39 with and without the check. | Test whether executing a check against the actual deliverable can catch these mistakes. [Failure audit and checklist](experiments.md#2026-10-21--batch-3-requirement-checklist-plan-30-and-failure-stop-as-a-reminder-plan-31-no) |
| The early-deliverable pilot scored 8/9 in both arms. The scheduler wrote candidate plans earlier in all three enabled runs. | Find which timeout cases have an artifact worth saving and measure how much time is available for another useful action. [PR #57](https://github.com/canyang25/BadgerForge/pull/57) |
| Loop recovery passed 1/2 enabled and 2/2 in control in the four-trial smoke. After the only live hint, the next command still contacted the same site. | Check signal coverage and whether an intervention changes the next command. [PR #58](https://github.com/canyang25/BadgerForge/pull/58) |

An audit of 100 distinct saved, graded runs across 13 tasks found 29
failures. Twelve failures across four tasks reached `TASK_COMPLETE`, eight
timed out, six stopped after commandless replies, and three stopped another
way. This sample includes the 22 recent pilot trials and spans several
agent configurations. It gives an upper bound on how many of these failures
a completion check could reach. Checkability, time remaining, and whether a
repair succeeds still need measurement.

The historical x86 graph control scored 46/89. WSL drift shortened its
effective time limits, so a fresh matched pair is the basis for measuring a
new change. Published Terminal-Bench results also show that changing
wall-clock limits can materially move harness scores. [BadgerForge full run](https://github.com/canyang25/BadgerForge/blob/09b9d813f8c5fe3a47f33de8bec9337cd1a3fb2c/docs/experiments.md#L6-L44) · [Benchmarks as Software](https://arxiv.org/abs/2611.08417)

## Research subtasks

1. **Audit where runs go wrong.** Replay available graded traces from several
   task families. Record whether the agent claimed completion, attempted a
   check of the stated requirement, wrote a candidate artifact, spent time
   repeating an outcome, or ran out of time. Include passing traces. Report
   how many distinct tasks each proposed change could plausibly reach and
   where we lack artifacts or timing data.
2. **Compare completion checks.** Use known passing and failing candidate
   states across different output types. Estimate how many violations each
   configuration can demonstrate, how often it would reject a passing
   candidate, and how much time and token budget it consumes. Use saved
   states where we have them. A small shadow trial can supply missing
   observations if completion checking is still promising after the audit.
3. **Walk the execution loop and deadlines.** Check the turns following a
   repeated outcome, a commandless reply, and an early-deliverable or recovery
   trigger. Estimate time spent in model calls, shell execution, and tool
   waits when timing is available. Pick one small loop change for comparison
   if the same problem appears across tasks.
4. **Decide whether task subtasks would help.** Look for dependencies or
   deliverables that the agent overlooks while it works. If those failures
   recur, consider a short list generated from the current task's requirements
   and updated using actual tool output. Compare it under the same budget
   with the current loop. Published results on planning vary by model.
   [Harness design study](https://arxiv.org/abs/2609.20804)

At the research checkpoint, put the strongest candidate alongside its
supporting traces, estimated coverage, costs, and what would count as a win
in a targeted comparison. Use that checkpoint to decide which implementation
PRs to open. Start with one change that has a measurable hypothesis across
tasks.

## What a completion check could look like

A completion check is a test run before submission when the agent claims
the task is done. It uses the public instructions and candidate artifacts
to test an explicit requirement. Harbor still scores the submitted result. For
example, the same check interface could take a program and an input to test
its behavior or take a structured output and test a constraint from the
instructions. Use task families and held-out tasks to sample coverage.

| Choice | Small configuration to investigate |
| --- | --- |
| Reference | The current agent loop. Use our checklist result as evidence about a prompt-based check. |
| Trigger | One check at the first completion claim. Measure how often the public instructions, observable artifacts, and remaining time support a concrete test. |
| Context | Compare an instruction-based check in a fresh context with a check the actor selects in its existing context. |
| Access | Inspect an artifact read-only, or execute a small test against a disposable copy when the requirement is behavioral. Consider richer environment snapshots for requirements about live services or preservation of initial state. |
| Verdict | Start in shadow mode. It records the check result while the ordinary candidate goes to Harbor. Record pass, concrete failure, or inconclusive, with the expected and observed result for a failure. |
| Budget and repair | Measure check cost against the time left in the original trial. If shadow evidence is promising, compare one bounded repair in the ordinary loop after a concrete failure. Pass, inconclusive, and low-time paths go to submission. |

I would investigate executable checks first. They target a recurring mistake
in our audit. Probe-and-Resume found that executing checks at completion
improved pass rate in its setup, at about 2.2 times the baseline model cost.
Its critic also rejected 60 of 282 first proposals that already passed.
Measure that tradeoff with our model and budget before committing to a
verifier. [Probe-and-Resume](https://arxiv.org/html/2610.21088v1#S4)

## First experiment

Use the saved traces to pick a small slice across different output types,
including tasks with passing and failing runs. The saved trials have grades
and command traces, and their artifact manifests are empty. Run a fresh
control sample and capture the relevant candidate files when the agent first
claims completion. Save the public task instructions, time remaining, and
Harbor's grade for that candidate.

Try one task-generic executable check on each captured candidate in an
isolated copy. Run it after the control trial so its time can be measured
alongside the time that was available at the completion claim. Compare its
verdict with Harbor's grade. Count demonstrated errors, flags on passing
candidates, inconclusive outcomes, and the extra seconds and tokens. Use
those results to decide whether a live test with one bounded repair is worth
running.

## Where the loop changes would fit

The agent proposes a command, the guard decides whether to run it, and the
shell observation goes back to the model. The current completion marker
sends the graph to submission. A loop change could act on a repeated
command-and-observation pattern before spending another turn. A commandless
stop could be studied through the existing nudge path. Deadline handling
could act while a required output is still missing. If we select a completion
check with repair, it would return the observed mismatch to the same loop
so the agent chooses the next command. [Current routing](../agent/graph/routing.py) · [OpenHands stuck detector](https://docs.openhands.dev/sdk/guides/agent-stuck-detector)

Investigate deadline handling next if traces show time is being spent before
the first viable artifact. For recovery, replay command-and-observation
patterns on passing and failing runs before choosing a trigger. Prefer an
intervention whose effect can be seen in the next action. The 403 smoke
shows why it is useful to measure the response to a hint as well as whether
the hint fired.

## PRs, pulls, and full-run checkpoints

PRs #57 and #58 are merged and pulled into `preston-test` at `e2eba49`. Each
selected implementation task gets a short-lived branch from the latest
`origin/preston-test` and a PR with its tests, dependencies, and pilot
evidence. After review and green checks, squash-merge into `preston-test` and
pull with `git pull --ff-only origin preston-test` before starting its
dependent task. [Promotion guide](promoting-changes.md)

- **After each PR** record the merge SHA, profile, test and pilot results,
  and next task. When a pilot checks a candidate artifact, record which
  artifact was checked, the verdict, and the final Harbor outcome.
- **After each major batch of two or three related implementation PRs** run
  the current control and the selected candidate on all 89 tasks, one trial
  per task per arm. This is the first full-run milestone for whichever
  change the research selects. Use one frozen SHA, the dataset at
  `7131e4375048a0e408a8fb404b5f499d726b695b`, the same model and flags apart
  from the experiment, and matched x86 clocks and per-task limits. Pass all
  89 task names to the launcher and preview both manifests.
  [Controlled runs](langgraph-evaluation.md#controlled-benchmark-runs)
- **After the full comparison** save both manifests, grader results, and
  compact trial exports. Compare which tasks gained or lost passes,
  activation coverage, timeouts, tokens, and elapsed time. Repeat a close
  comparison before changing the default profile. [Experiment log](experiments.md)

## Cleanup reminder

At each checkpoint, delete disposable scratch files, generated caches, and
superseded exports after verifying the retained evidence. Keep user files,
the final exports, and the manifests and artifacts needed for active work or
reproducing the result.
