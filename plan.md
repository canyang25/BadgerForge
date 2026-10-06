# Plan

Leaderboard score = `TB score − 0.01 × (total tokens / 1M)`. Tokens cost
points, so every result reports both. Numbers and what we learned from each
run live in [docs/experiments.md](docs/experiments.md).

## How we test a change

- **Dev slice:** 7 tasks from `terminal-bench/terminal-bench-2-1`:
  `chess-best-move`, `configure-git-webserver`, `fix-code-vulnerability`,
  `log-summary-date-ranges`, `polyglot-c-py`, `regex-log`, `sqlite-with-gcov`.
  Left out: `build-cython-ext` (broken reference solution) and the two qemu
  tasks (can't run on Apple Silicon). **Saturated as of 2026-10-06:** six
  tasks always pass and chess-best-move never does, so it can no longer show
  an improvement. Being replaced — see below.
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

**Next: rebuild the dev slice.** The current one can't measure improvements
any more (experiments.md, 2026-10-06). Run all 89 tasks once on x86, which
gives our first full score, then choose ~10 tasks with mixed results as the
new slice. Re-run the current config on it as the new baseline before any
further item below. Owner: ruoshi.

| # | Experiment | Question it answers | Owner |
|---|---|---|---|
| 1 | ~~`LLM_REASONING_EFFORT=medium`~~ | Costs score: 0.76 vs 0.86. Staying on default — see experiments.md | ruoshi ✅ |
| 2 | ~~Remove `agent/loop_guard.py`~~ | Keep it: same score, 46% more tokens without it. The 0.86 was the truncation fix | ruoshi ✅ |
| 3 | Turn cap well below 100 | **On hold:** a trial passed at turn 84 (2026-10-06), so the premise doesn't hold. Revisit on the new slice | |
| 4 | Parse model output into Pydantic models, retry on bad format | Fewer wasted turns on malformed replies? | |
| 5 | ~~Why `chess-best-move` never passes~~ | Not by itself: it's a text-only model trying to read an image, without surveying the environment or installing tools. Root causes are general → #6 | ruoshi ✅ |
| 6 | ~~System prompt: survey environment, prefer tools, no raw data~~ | No measurable gain (0.81 vs 0.86, within noise); the model mostly ignored the rules. Not merged | ruoshi ✗ |
| 7 | ~~Environment probe run by the agent code before turn 1~~ | No evidence it helps (0.71 vs 0.86, partly a degraded gateway); chess-best-move saw the font and still ignored it. Not merged | ruoshi ✗ |
| 8 | Summarise binary- or matrix-like command output in code | Fewer tokens wasted on dumps the model can't read? | |
| 9 | `scripts/score.py` reports gateway health | Implemented in #17: flags trials over 40 s/turn **and** under 30 tok/s, lists connection failures | ruoshi → #17 |
| 10 | ~~Lower reasoning effort for one turn after a truncated, command-less turn~~ | Doesn't recover: got a command 65% of the time vs 61% without it. Not merged. Raising `LLM_MAX_TOKENS` untested | ruoshi ✗ |

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
