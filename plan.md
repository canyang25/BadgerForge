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
0.584 (52/89, 10-12) with medium reasoning effort. Since then, with changes
that moved nothing measurable: 0.494 (44/89), 0.551 (49/89), 0.607 (54/89,
main at `925566b`, 10-26) and 0.528 (47/89, plan 35, 10-28). Runs 3–7: mean
49.2/89 (0.553), standard deviation 4 tasks.**

**Next: the writeup** (deadline Wed 2 Dec 2026, 23:59 Madison time, Kaggle).
The submission configuration is main at `925566b`, whose agent is the one in
full run 6 (full runs 3–5's plus Preston's parser fixes #34 and #36). A PR
that changes the agent needs a new full run before the estimate applies to it.
Further experiments only if they touch many tasks and we can check that they
actually fire (plan 33 is the best left). Plan item numbers are not PR numbers.
Before long runs on the Windows laptop, see docs/setup-windows.md (the blue
screen note).

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
| 14 | Empty answers: no content, finish reason not `length` | Half the replies in the give-ups of full runs 2 and 3, and 6 of batch 2's 11 give-ups had no cut-off at all. The act nudge recovers most, but llm.py labels them "cut off", which they aren't. Own handling? Plan 35 tried one: no gain | |
| 15 | Tell the model how much time is left | Later: Harbor doesn't give our agent the limit, and none of full run 3's 10 timeouts had a scoring state at the deadline (4 of 53 timeouts in all runs did) | |
| 16 | ~~Check the work before TASK_COMPLETE, at medium or full effort~~ | No: 26 / 27 / 25 of 39 (none / medium / full effort) on 13 tasks. The check mostly re-confirms; when it acts it breaks working solutions as often as it fixes. Not merged (`ruoshi/feat-verify-before-done`) | ruoshi ✗ |
| 17 | ~~System prompt says there is no network; TB 2.1 tasks have it~~ | No: in full run 3 no reply says it's offline, 33 trials installed or downloaded (199 commands, 1 network error). Dropped | ruoshi ✗ |
| 18 | ~~Compact old turns on long tasks~~ | Not doing: turn time is in output, not input (sqlite-db-truncate: 7.7k input, 62 s/turn; path-tracing-reverse: 62k, 31 s/turn), and tokens no longer score | ✗ |
| 19 | ~~Tooling: gateway 502s (`InternalServerError`) count as gateway failures~~ | Done in `run_full.sh resume`, `score.py`, `export_trials.py` | ruoshi ✅ |
| 20 | ~~Sampling as on the Qwen3.8-27B model card: temperature 1.0, top_p 0.95, top_k 20~~ | No: 17/39 vs 18/39 at 0.2, 25% slower turns, more cut-offs (29 vs 21). Not merged (`ruoshi/feat-sampling`) | ruoshi ✗ |
| 21 | ~~Looser give-up rule: 8 command-less turns, or never give up~~ | No: never giving up kept 5 trials alive and all 5 ran out the clock. The same data covers 8: those 5 would still fail. Keep 4 | ruoshi ✗ |
| 22 | ~~Long commands in the background and polled, command limit 60 → 120 s~~ | Not doing: small gain (65 commands hit 60 s in full run 3, mostly in never-passing tasks), and mini-swe-agent does no better (30 s limit, no background jobs) | ✗ |
| 23 | ~~Wait for apt/dpkg left running by the image before starting~~ | Done: six full-run-3 installs failed on the dpkg lock (three of those trials passed anyway). In real runs since (batch 2, full run 4: 206 trials) setup took at most 0.5 s, so it never fires on a resident process. If it ever does, check `/proc/locks` for the dpkg and `/var/lib/apt/lists/lock` locks instead | ruoshi ✅ |
| 24 | ~~Read mini-swe-agent's prompt and loop against ours~~ | Done 10-14. Biggest difference: a cut-off reply is dropped from the history and the model is told to think briefly (→ #25). Others: no turn cap (#3), says every command runs in a fresh shell (#27), quiet env vars (#28), advice when output is long (#29) | ruoshi ✅ |
| 25 | ~~What a cut-off reply leaves behind: its 2000-char tail (as now), the tail plus a "be concise" nudge, or nothing (mini-swe-agent)~~ | No: 18 / 19 / 21 of 39, within noise; cut-offs are 1–2% of turns at 16k and medium. Dropping costs 25% more tokens per task. Not adopted; code on `ruoshi/feat-cutoff-handling` | ruoshi ✗ |
| 26 | ~~Tooling: resume must never rerun a whole job~~ | Done: `run_full.sh resume` pins `job_name` (harbor drops it from config.json when it equals the default), and also reruns container-start timeouts. Worked in full run 4's blue-screen restart: none of 74 finished trials rerun | ruoshi ✅ |
| 27 | Tell the model each command runs in a fresh shell (`cd` and env vars don't carry over) | From mini-swe-agent. Check transcripts for commands that failed on a lost `cd` first | |
| 28 | Quiet env vars for commands: `PAGER=cat`, `PIP_PROGRESS_BAR=off`, `TQDM_DISABLE=1` | From mini-swe-agent. Check how much observation text progress bars take first | |
| 29 | When output is cut, tell the model to use head/tail/grep or a file | From mini-swe-agent. Probably small | |
| 30 | ~~Requirement checklist before finishing~~ | No: 20/39 with and without on the 13 tasks that most often finish wrong. It always ran, but its checks were looser than the graders'. Not merged (`ruoshi/feat-checklist-and-guard`) | ruoshi ✗ |
| 31 | ~~Loop guard: remind instead of stopping after 8 failures in a row~~ | No measured gain: in batch 3 it never fired; in full run 5 it fired twice, both on trials that failed anyway. Not merged | ruoshi ✗ |
| 32 | Stop on 8 failures in a row only when every output is the same | Full run 5's build-pov-ray broke its own container (`kill -9 -1`) and kept going. Idea only | |
| 33 | Progress check every ~10 turns or after 3 identical failures: say what changed, else switch approach | 5 sometimes-solved tasks get stuck on one approach (10-20 analysis). Define how to tell it fired before running | |
| 34 | Write the deliverable as soon as there's a plausible answer, then improve it | 3 sometimes-solved tasks think without ever writing the file (10-20 analysis) | |
| 35 | ~~Never run a command from cut-off reasoning; store an empty reply as an empty message (PR #37)~~ | No: batch 4 10/30 vs 14/30, full run 7 47/89 vs run 6's 54, no failure traced to it. Tail commands 23 → 0, but give-ups 6 → 10: empty replies now count toward the 4-strike rule. Not merged | preston ✗ |
| 36 | ~~Run a bash block that has no closing fence when the reply finished normally~~ | Not doing: 34 of 23,144 recorded replies (0.15%, 25 trials), mostly build-pov-ray and protein-assembly. Each costs one turn, and after the nudge the next turn ran a command 31 times (7 the same one). Accepting them would also run 5 degenerate repetitions, 2 half statements and 5 commands trailed by leftover tool-call XML | ✗ |

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
