# Promoting individual changes

Promote one concern per PR. State the exact target base and prerequisite
commits, include its tests, and record the isolated application/test result.
Keep experimental behavior off until its scored comparison supports adoption.
Merge into `preston-test` for integration; promotion to `main` is a separate
decision. Do not rewrite the integration branch to make a patch look independent.

## Check a candidate without changing the checkout

Use local, trusted commits and the project's Python environment:

```bash
.venv/bin/python scripts/check_promotion.py --base main <change-commit>
# If the change has prerequisites, supply them first, in order:
.venv/bin/python scripts/check_promotion.py --base main <prerequisite> <change>
```

The checker resolves refs to exact commits, clones the local repository into
a temporary directory, applies only the specified commits, and runs `pytest`
there. It never fetches, switches the source checkout, or updates the target
branch. Project imports come from the temporary candidate, including when the
Python environment has an editable install of `preston-test`. The report lists
the commits, conflicts, and test output. A conflict or failing test exits 1.

The default is the full `tests/` suite. Repeat `--test <pytest-target>` to run
specific tests, and say in the PR when validation was limited. `--apply-only`
reports `applied_without_tests`, which is not a passing test result. Tests use
the active environment: this does not validate installation in a fresh runtime.
No credentials are loaded, and the inherited gateway API key is removed from
the test process. Run only trusted tests; the checker is not a security sandbox.

## Independent promotion ports: prepared 2026-10-29

The older coupled diffs below now have independently tested promotion branches.
They were rebuilt from main at `cb8c3d3`, reusing code from `preston-test` at
`8de298f`. No integration history was rewritten and no change landed on main.
The exact full SHAs and prerequisites are in
[`eval/promotion-ports.json`](../eval/promotion-ports.json).

| Selectable concern | Own commits, in order | Prerequisite | Passing tests |
|---|---|---|---:|
| Graph definitions, then switch the loop | `09b9054`, `a5255aa` | main | 94, then 100 |
| Cancellation fix | `349c4f8` | Graph core | 104 |
| Progress checks with trigger tracing | `2ea320a` | Core + cancellation | 110 |
| Shaping helpers, then optional wiring | `844829a`, `ffc7784` | Core + cancellation | 120, then 124 |
| Early-deliverable checkpoint | `4e32f8b` | Core + cancellation | 112 |
| Controlled experiment launcher | `8f5c060` | main; no graph | 108 |

The branches are `codex/promote-graph-core`, `codex/promote-graph-cancellation`,
`codex/promote-graph-progress`, `codex/promote-graph-shape`,
`codex/promote-graph-deliverable`, and `codex/promote-experiment-launcher`.
Each change is under 400 changed lines. The core's definitions and loop switch,
and shaping's helpers and wiring, are separate commits for review.

Each graph branch also matches the exact main loop on ten scripted cases with
its feature off: model requests, temperatures, commands, tokens, and stopping
metadata. The checkpoint contains no launcher change; the launcher contains no
graph code or graph documentation dependency. Enabled feature tests establish
activation and routing, not a score improvement. All feature defaults remain off.

For example, verify cancellation alone or shaping alone:

```bash
.venv/bin/python scripts/check_promotion.py --base main 09b9054 a5255aa 349c4f8
.venv/bin/python scripts/check_promotion.py --base main 09b9054 a5255aa 349c4f8 844829a ffc7784
```

Each experiment is selectable without either sibling experiment. Combining
sibling patches still needs a wiring rebase and another validation run; do not
assume their changes to the same routing file will cherry-pick together. The
integration branch already tests all three together. On the plain loop, use
only the launcher's control or turns150 profile; the other profiles need their
corresponding agent feature, and activation must be checked in the node trace.

## Original commits: historical audit 2026-10-29

Target: `main` at `cb8c3d3c36641feff342dc9729cafa7d8d05f78c`.
These are local unit-test results, not new model benchmarks. Each row starts
from that target and applies only the listed commits, in order.

| Concern | Commits / prerequisite | Result |
|---|---|---|
| Basic LangGraph port | `6eaa882` | Clean; 100 tests pass |
| Progress trigger tracing (#44) | `6eaa882`, `e343cac`, `db3ee32` | Clean; 109 tests pass |
| Shaping diagnostics fix (#42) | `6eaa882`, `e343cac`, `0754f27` | Clean; 123 tests pass |
| Live smoke record (#48) | `cdf1284` | Clean; main's 94 tests pass; no agent code change |
| Initial cancellation context (#43) | `6eaa882`, `e343cac`, `3ca300a` | Clean; 111 tests pass. Picking onto the core alone conflicts in graph wiring |
| Controlled launcher (#46) | `46141e0` | Code is separate; original PR conflicts in graph documentation and `plan.md` |
| Early deliverable (#47) | `8360066` | Requires graph wiring and launcher support; original PR is not a standalone main cherry-pick |

`e343cac` originally combined progress and shaping. Neither later fix requires
the other later fix, as the isolated test rows show, but selecting only one
original experiment still needs a split of that earlier commit. Feature flags
make experiments independently activatable; they do not remove code dependencies.

The main-sync commit `6f62359` includes fixes already on main. Do not replay it
onto main just to satisfy a documentation conflict. Port the affected concern
and its tests, adjusting the destination's docs in that same promotion PR.
Do not merge all of `preston-test` to acquire a single experiment.

## Remaining validation and tooling

- Add dataset revision and selected-task dirtiness to experiment manifests;
  the current manifest pins the agent but can miss changed benchmark inputs.
- Run scored loop/graph parity and targeted failure comparisons before
  adopting behavior. The completed two-task smoke was 6/6 in each arm and
  does not establish an improvement.
