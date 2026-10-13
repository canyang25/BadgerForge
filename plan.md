# Plan

Leaderboard score = `TB score − min(0.01, 0.01 × tokens per task / 100M)`.
The penalty is capped below one solved task (1/89), so tokens only break ties:
passing more tasks comes first. Every result still reports both. Numbers and
what we learned from each run live in [docs/experiments.md](docs/experiments.md).

## How we test a change

- **Dev slice (since 2026-10-08):** 10 tasks from `terminal-bench/terminal-bench-2-1`,
  picked from the first full run so that each way we fail shows up and most
  tasks can go either way: `compile-compcert`, `extract-elf`,
  `feal-linear-cryptanalysis`, `largest-eigenval`, `modernize-scientific-stack`,
  `portfolio-optimization`, `regex-log`, `reshard-c4-data`,
  `sqlite-db-truncate`, `write-compressor`. **Baseline 0.40** (12 of 30
  trials). Runs on the Windows box, about 2.5 h for 3 trials at concurrency 2.
  The old 7-task slice saturated: six tasks always passed.
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

**Full runs: 0.438 (39/89, 10-07) → 0.539 (48/89, 10-11) with #11 and 16k →
0.584 (52/89, 10-12) with medium reasoning effort.**

**Next: #17, then #15.** #16 didn't help (experiments.md, 2026-10-12). Full
run 3's remaining failures: 15 wrong answers, 10 timeouts, 7 give-ups. First
check full run 3's transcripts for #17 before spending a run on it.

| # | Experiment | Question it answers | Owner |
|---|---|---|---|
| 1 | ~~`LLM_REASONING_EFFORT=medium`~~ | Costs score on the old slice: 0.76 vs 0.86. Reversed at full scale by #13 | ruoshi ✅ |
| 2 | ~~Remove `agent/loop_guard.py`~~ | Keep it: same score, 46% more tokens without it. The 0.86 was the truncation fix | ruoshi ✅ |
| 3 | Turn cap (now 100) | Reversed: in the full run 6 tasks hit 100 turns with time left, and compile-compcert passed at 99. Try raising it | |
| 4 | Parse model output into Pydantic models, retry on bad format | Fewer wasted turns on malformed replies? | |
| 5 | ~~Why `chess-best-move` never passes~~ | Not by itself: it's a text-only model trying to read an image, without surveying the environment or installing tools. Root causes are general → #6 | ruoshi ✅ |
| 6 | ~~System prompt: survey environment, prefer tools, no raw data~~ | No measurable gain (0.81 vs 0.86, within noise); the model mostly ignored the rules. Not merged | ruoshi ✗ |
| 7 | ~~Environment probe run by the agent code before turn 1~~ | No evidence it helps (0.71 vs 0.86, partly a degraded gateway); chess-best-move saw the font and still ignored it. Not merged | ruoshi ✗ |
| 8 | Summarise binary- or matrix-like command output in code | Fewer tokens wasted on dumps the model can't read? | |
| 9 | ~~`scripts/score.py` reports gateway health~~ | Merged in #17: flags trials over 40 s/turn **and** under 30 tok/s, lists connection failures | ruoshi ✅ |
| 10 | ~~Lower reasoning effort for one turn after a truncated, command-less turn~~ | Doesn't recover: got a command 65% of the time vs 61% without it. Not merged. Raising `LLM_MAX_TOKENS` untested | ruoshi ✗ |
| 11 | ~~Short command-less replies: stronger nudge, temperature 0.7 for one turn~~ | Yes: no give-ups on short replies (3 of 7 at 16k), and the next reply has a command 82% of the time (65% before). Passes 14/30, within noise | ruoshi ✅ |
| 12 | ~~`LLM_MAX_TOKENS=16384`~~ | Yes, on top of #11: 19/30 vs 14/30, cut-off give-ups 3 vs 8. Costs time: 46 vs 26 s/turn, timeouts 6 vs 2. Now the default | ruoshi ✅ |
| 13 | ~~`LLM_REASONING_EFFORT=medium`, again~~ | Slice: a wash (18 vs 19/30). Full run: 52/89 vs 48/89, timeouts 20 → 10, wrong answers 5 → 15, turns 12 vs 28 s. Now the default | ruoshi ✅ |
| 14 | Empty answers: no content, finish reason not `length` | Half the replies in the give-ups of full runs 2 and 3. The act nudge recovers most, but llm.py labels them "cut off", which they aren't. Own handling? | |
| 15 | Tell the model how much time is left | 7 tasks still time out at medium, at 12 s/turn (path-tracing, gcode-to-text, …). Does it finish sooner? | |
| 16 | ~~Check the work before TASK_COMPLETE, at medium or full effort~~ | No: 26 / 27 / 25 of 39 (none / medium / full effort) on 13 tasks. The check mostly re-confirms; when it acts it breaks working solutions as often as it fixes. Not merged (`ruoshi/feat-verify-before-done`) | ruoshi ✗ |
| 17 | System prompt says there is no network; TB 2.1 tasks have it | Does that line stop the model from installing what a task needs? | |
| 18 | Compact old turns on long tasks | Long tasks resend 30–40k input tokens per turn. Faster turns, fewer timeouts, without the lost passes Badger Agents saw? | |
| 19 | Tooling: treat gateway 502s (`InternalServerError`) as gateway failures in `run_full.sh resume`, `score.py` and `export_trials.py` | Today a 502 outage counts as a finished trial and isn't rerun | |

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
