# Selecting changes from preston-test

`preston-test` is the integration branch. Focused commits on that branch are
the selectable units; a permanent branch for every feature is unnecessary.
The earlier `codex/promote-*` snapshots are retired. Their retirement changes
no agent code, model settings, main history, or frozen benchmark source.

## Keep new changes separable

1. Make one logical change per short-lived work branch and PR. Keep its code,
   tests, and relevant documentation together; split unrelated concerns.
2. Name its prerequisites. Keep the graph foundation separate from optional
   nodes, and keep independent evaluation tooling out of agent changes.
3. Review and test the PR, then squash merge it into one focused commit on
   `preston-test`. Delete the temporary work branch after merging.
4. Keep optional behavior off until a controlled benchmark supports adoption.
   A flag controls activation; it does not remove a code dependency.

## Select changes for main when needed

Create one temporary branch from the current main target. Cherry-pick only
the chosen integration commits and their prerequisites, in order, then review
the full resulting diff and run the destination's tests. Use a PR into main;
promoting a change remains a separate decision from integration testing.

An older commit may contain unrelated changes or have patch-context conflicts.
Split or adapt that patch in the temporary main PR, explaining the adjustment
and keeping its regression tests. Preserve `preston-test`'s shared history.
Do not merge the entire integration branch to obtain one experiment.

The source catalog is
[`eval/promotion-commits.json`](../eval/promotion-commits.json). Every recorded
commit belongs to `preston-test` history. `verified_chain` means the named
chain applied and passed tests against the recorded target at the audit date.
`needs_split` and `needs_preparation` are work still required in a future main
PR; they are not promises that a direct cherry-pick will work.

## Validate without changing either branch

```bash
.venv/bin/python scripts/check_promotion.py --base main <selected-commit>
# Explicit prerequisites come first:
.venv/bin/python scripts/check_promotion.py --base main <prerequisite> <selected-commit>
```

The checker resolves exact commits, makes a disposable local clone, applies
only those commits, and runs the full `tests/` suite in that candidate. It
reports conflicts and failing tests and rejects project imports leaking from
an editable installation of the source checkout. It never switches the source
checkout, updates main, fetches, installs dependencies, or loads credentials.
The inherited gateway API key is removed from the test process.

Repeat `--test <pytest-target>` to limit the suite and disclose that limit in
the PR. `--apply-only` reports `applied_without_tests`, not a passing test run.
Tests use the active Python runtime; dependency installation in a fresh runtime
and any behavior-changing benchmark remain separate checks. Run trusted tests:
the disposable checkout is not a security sandbox.

## Existing integration changes

Audit target: main at `cb8c3d3`, on 2026-10-29. These are source application and
unit-test results, not new model benchmark scores.

| Concern | Integration commit | Prerequisite / preparation |
|---|---|---|
| Graph foundation | `6eaa882` | Applies to the recorded main target; 100 tests passed |
| Original optional nodes | `e343cac` | Combines progress and shaping; split before selecting only one |
| Cancellation context | `3ca300a` | Original diff needs core + optional-node context; that chain passed 111 tests. Adapt the small fix for core-only promotion |
| Progress trigger tracing | `db3ee32` | Core + original optional nodes; 109 tests passed |
| Shaping diagnostics | `0754f27` | Core + original optional nodes; 123 tests passed |
| Controlled launcher | `46141e0` | Agent-independent code; prepare its docs/plan against the destination |
| Deliverable checkpoint | `8360066` | Separate its feature hunks from incidental launcher and routing context |
| Promotion checker | `8de298f` | Applies to the recorded main target; 100 tests passed. Refresh accompanying workflow docs for the destination |
| Dataset provenance | `0dd5be1` | Requires the controlled launcher; preserve dirty-input regression tests |
| Initial live smoke record | `cdf1284` | Applies without graph code; main's 94 tests passed |

The original optional-node commit is legacy combined history. Do not rewrite
that shared commit or create permanent copies of every possible split. The
individual nodes already live in separate modules; prepare the selected wiring
when a concrete main PR is requested. The main-sync commit `6f62359` includes
fixes already on main and should not be replayed merely to repair doc context.

## Validation still required

Dataset provenance is implemented in #51; see
[the input-provenance guide](experiment-provenance.md). It records the dataset
revision and detects changes to selected task files before a controlled run.
The [local loop/graph control comparison](experiments.md#2026-10-30--looplanggraph-control-ten-tasks-three-attempts-per-arm)
is recorded: 17/30 and 21/30, with 52 matching offline recorded replays.
This completes local control collection, without establishing general parity
or improvement. Targeted enabled-feature evidence and full 89-task native-x86
validation still gate adoption. The earlier two-task checkpoint pilot passed
6/6 in each arm and did not establish an improvement. No main promotion or
default change is part of this workflow.
