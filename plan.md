# Plan

Leaderboard score = `TB score − 0.01 × (total tokens / 1M)`. Tokens cost
points, so every result reports both. Numbers and what we learned from each
run live in [docs/experiments.md](docs/experiments.md).

## How we test a change

- **Dev slice:** 7 tasks from `terminal-bench/terminal-bench-2-1`:
  `chess-best-move`, `configure-git-webserver`, `fix-code-vulnerability`,
  `log-summary-date-ranges`, `polyglot-c-py`, `regex-log`, `sqlite-with-gcov`.
  Left out: `build-cython-ext` (broken reference solution) and the two qemu
  tasks (can't run on Apple Silicon).
- **3 trials per task, always.** One task returned pass, fail and timeout
  across three trials of the same code. A difference smaller than the
  per-task spread in `scripts/score.py` is noise.
- **One change per run.** The 0.86 result measured two changes together and
  we still can't say which did the work. Don't repeat that.
- **Full 89-task runs** happen on x86 (Windows/WSL2, see
  [docs/setup-windows.md](docs/setup-windows.md)), occasionally, to check the
  dev slice isn't misleading us. The final submission is all 89, one attempt
  each.

## Phase 1 — MVP ✅

| Step | Result |
|---|---|
| Starter agent in the repo, layout per CONTRIBUTING | #3 |
| BadgerBrain via `.env.op` + `op run`, no key on disk | #3 |
| `scripts/score.py` with tests | #4 |
| Baseline, dev slice × 3 | **TB 0.57, 3.1M tokens** — #6 |
| First fix: stop storing truncated reasoning | **TB 0.86, 1.4M tokens** — #8, #12 |

Also landed: retries for gateway drops (#5), CI (#10), reasoning-effort switch
(#9).

## Phase 2 — cheap experiments on the current agent

Small, measurable changes before any rewrite. Each is one dev-slice run
compared against the current best.

| # | Experiment | Question it answers | Owner |
|---|---|---|---|
| 1 | `LLM_REASONING_EFFORT=medium` | Does less thinking cost score, or just tokens? | ruoshi |
| 2 | Remove `agent/loop_guard.py` | Is the loop guard earning its place, or was #8 all the truncation fix? | ruoshi |
| 3 | Turn cap well below 100 | Nothing has passed after ~35 turns; can we stop sooner? | |
| 4 | Parse model output into Pydantic models, retry on bad format | Fewer wasted turns on malformed replies? | |
| 5 | Why `chess-best-move` never passes | Is it fixable without task-specific code? | |

## Phase 3 — LangGraph

Rebuild the loop as a graph once Phase 2 stops moving the numbers. The
current agent's score is the bar the graph version has to clear before it
replaces it.

- Port the existing loop to LangGraph with no behaviour change, and confirm
  it matches the current numbers
- Observability: logging and tracing per node, so we can see where tokens go
- Then experiment: planning and verification nodes, agent instructions,
  single vs multiple agents

## Open questions

- ~~TB 2.0 or 2.1?~~ **2.1**, confirmed 9/23. The challenge repo still says
  2.0, so the writeup must say which we used.
- ~~Where do full runs happen?~~ Windows/WSL2 (ruoshi has one).
- Starter code has no LICENSE upstream; ask Chris before we submit an MIT repo
  built on it.
- LangSmith for tracing sends transcripts to a third party. Fine for public
  benchmark tasks, but agree on it before turning it on.
