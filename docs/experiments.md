# Experiment log

Newest first. One entry per run we want to remember: what changed, what the
numbers were, what we learned. Numbers come from `scripts/score.py`.

## 2026-10-08 — First full run, and a new dev slice

- Code: `main` at `294e023` (agent unchanged since the truncation fix). x86
  Windows/WSL2 laptop, concurrency 2, one trial per task, 11 h.
- Results: `eval/results/full-run-1.csv`, one row per trial
  (`scripts/export_trials.py`). Gateway median 19 s/turn, one slow trial
  (regex-chess).

| | Full run |
|---|---|
| TB score | **0.43820** (39/89) |
| Total tokens | 52,254,395 (587k per task) |
| Leaderboard score | 0.43814 |

Why the other 50 failed:

| Cause | Tasks |
|---|---|
| Gave up: four command-less turns in a row (`no_action` stop) | 25 |
| Agent timeout | 9 |
| Hit the 100-turn cap with time left (the CSV says `wrong_answer`) | 6 |
| Finished, tests failed | 7 |
| Verifier timed out | 3 |

**The 7-task slice overstated our progress.** 0.86 there, 0.44 here. Badger
Agents measured the unmodified starter at 40/89, so at full scale our changes
don't show yet.

**Giving up is half of all failures, and it is mostly the thinking budget.**
Of the last four replies before each give-up (100 replies), 74 were cut off
at the 8192-token output limit and 26 were one-line "Let's start by
exploring…" replies with no command. 17 tasks were cut-offs only, 4 short
replies only, 4 mixed. The short replies come back in about a second, so the
model isn't thinking at all. Their wording drifts from turn to turn but the
model never acts, and the nudge doesn't change that. They are also random:
two of the four tasks that quit in 3 s on 10-07 passed 2/2 on 10-08.

**New dev slice.** Two more trials on 20 candidates
(`eval/results/slice-candidates.csv`; gateway median 29 s/turn, slower than
the night before), then 10 picked so that each failure mode is in and most
tasks can go either way:

| task | 3 trials | why it's in |
|---|---|---|
| extract-elf | wrong, pass, wrong | finishes; answer sometimes wrong |
| largest-eigenval | timeout, pass, timeout | timeouts |
| compile-compcert | wrong, wrong, pass | 100-turn cap |
| reshard-c4-data | gave up, gave up, pass | cut-off thinking |
| sqlite-db-truncate | gave up, pass, gave up | cut-off thinking |
| feal-linear-cryptanalysis | gave up ×3 | cut-off thinking, quick to run |
| write-compressor | gave up ×3 | cut-off thinking, quick to run |
| modernize-scientific-stack | gave up, pass, pass | short replies |
| portfolio-optimization | gave up, pass, pass | short replies |
| regex-log | pass ×3 | guard: should keep passing |

Baseline **0.40**, 311k tokens per task. The three baseline trials come from
two nights with different gateway speeds, so treat ±1 trial as noise.

## 2026-10-07 — Scoring rule changed

The token penalty is now `min(0.01, 0.01 × tokens per task / 100M)`
([Kaggle evaluation page](https://www.kaggle.com/competitions/OpenAgent-Coding/overview/evaluation)),
replacing `0.01 × total tokens / 1M`. It is capped below one solved task, so
it only breaks ties. `scripts/score.py` uses the new rule.

Leaderboard rows in the entries below use the old rule. Under the new one our
penalty is about 0.00002 (after the fix: 0.85714 → 0.85712; medium:
0.76190 → 0.76189), so read them as TB score. The full-scale extrapolation in
the reasoning-effort entry no longer applies; the decision to stay on the
default is unchanged, since medium passes fewer tasks.

## 2026-10-06 — Recovery turn after truncation (plan Phase 2 #10) ✗

- Code: branch `ruoshi/feat-truncation-recovery` (`a4229cb`, not merged).
  After a turn that is truncated and gives no command, the next request uses
  `reasoning_effort=medium`; the turn after goes back to the default.
  Everything else as the current agent.
- Results: `eval/results/truncation-recovery.csv`. Gateway healthy: median
  11 s/turn, no slow trials, no connection failures.

| | Current | With recovery turn |
|---|---|---|
| TB score | **0.8571** | 0.8095 |
| Total tokens | **1,442,339** | 1,723,675 (+20%) |
| Leaderboard score | **0.8427** | 0.7923 |

**Not merging — the recovery turn doesn't recover.** It fired 26 times and got
a command back 17 times (65%). Without it, across the previous four runs, the
turn after a truncated, command-less turn produced a command 72 times out of
119 (61%). Once the model is stuck on a hard step, one notch less effort
doesn't get it out: a third of the time it still thinks past the budget.

Neither gap in the table comes from the change:

- regex-log's one failure: the recovery turn wrote the first draft of the
  answer, but full-effort turns rewrote it six more times, ending with an edit
  that stripped every space out of the regex. The container has no Python, so
  the agent couldn't test what it wrote.
- configure-git-webserver ran one trial to 84 turns and 1.5M tokens, with one
  truncation and one recovery turn, and passed. That trial alone adds more to
  the total (+342k) than the whole difference (+281k).

### Finding: a pass at turn 84

That configure-git-webserver trial passed at turn 84. Phase 2 #3 rested on
"nothing passes after ~35 turns"; a 40-turn cap would have failed this trial.
#3 is on hold until a broader slice shows how many passes come late.

### Finding: the dev slice is saturated

| Run | TB score |
|---|---|
| Current config, run twice | 0.8571, 0.8571 |
| System prompt (#6) | 0.8095 |
| Environment probe (#7) | 0.7143, partly a degraded gateway |
| Recovery turn (#10) | 0.8095 |

In both runs of the current config, the six tasks other than chess-best-move
passed all 36 trials, and chess-best-move has never passed. On this slice a
change can only tie or lose: six tasks have no headroom and the seventh is out
of reach. Losing one trial is expected noise. If one trial in 30 fails by
chance, which fits 36/36, a run of 18 drops at least one about 46% of the
time.

So the last three experiments didn't show their changes are useless. They
showed this slice can't tell. Before more Phase 2 work, rebuild the slice from
tasks the agent sometimes passes: one trial of all 89 tasks on x86, which also
gives our first full score, then ~10 tasks with mixed results.

## 2026-10-05 — Environment probe in code (plan Phase 2 #7) ✗

- Code: branch `ruoshi/feat-env-probe` (`a62e6b6`, not merged). Before turn 1
  the agent runs a fixed shell probe — working directory, non-standard
  top-level directories, package managers, network reachability — and appends
  the ~400-character result to the task instruction. Nothing task-specific; a
  unit test fails if the probe ever names a task.
- Results: `eval/results/env-probe.csv`. Three trials lost to
  `APIConnectionError` (one each of chess-best-move, configure-git-webserver,
  fix-code-vulnerability) were dropped and re-run with the same code.

| | Current | With probe |
|---|---|---|
| TB score | **0.8571** | 0.7143 |
| Total tokens | 1,442,339 | **1,309,838** (−9%) |
| Leaderboard score | **0.8427** | 0.7012 |

**Not merging.**

It works mechanically: the survey reached the model in every trial. But the
case it was built for didn't move. chess-best-move saw `/fonts: noto.ttf` in
its first message and still never used it (0/3; one trial installed a chess
engine and still couldn't read the board). Having the information isn't
enough — connecting "a font file" to "this is what drew the board" is a
reasoning step the model doesn't make.

Where the three lost trials went:

| Trial | Cause |
|---|---|
| regex-log, timed out at 11 turns | Gateway degraded: 612 s per turn, so 15 minutes bought 11 turns. Not the agent |
| polyglot-c-py, stopped at 4 turns | Four consecutive turns truncated mid-thought → no-action stop |
| regex-log, stopped at 4 turns | Same |

That early stop happened 0 times in the 84 trials of the other four runs and
twice here, which looks suspicious. But first-turn behaviour didn't change
(turn 1 truncated in 6/21 trials here and 6/21 in the control; first command
exploratory in 15/21 vs 13/21), so there's no mechanism tying it to the
probe, and with five runs to compare, one of them showing two by chance is
roughly a 1-in-5 event.

So: no evidence it helps, can't rule out that it hurts, and the case that
motivated it failed. A re-run on a healthy gateway wouldn't change the
decision, so we didn't spend one.

### Side findings

**A degraded gateway silently spoils a run.**

| Run | Seconds per turn, median | Mean |
|---|---|---|
| Control | 15 | 19 |
| Other runs | 10–13 | 11–18 |
| This run | 17 | **85** |

Between 16:39 and 16:51 UTC turns took about ten minutes. The retry policy
from #5 (300 s timeout, 5 attempts) saves a trial when the connection drops,
but when the gateway is merely slow it spends the 15-minute task budget
waiting. Nothing in `scripts/score.py` shows this; we only found it by
looking at timestamps. → Phase 2 #9.

**The four-strike no-action stop can kill a task before it starts.** It was
added in #8 to stop a model that emitted the same truncated thought nine
times. On a task that needs hard thinking from turn 1, four truncated turns in
a row ends the task before a single command has run — both early stops above
passed 3/3 in the control. → Phase 2 #10.

## 2026-10-05 — System prompt: environment, tools, raw data (plan Phase 2 #6) ✗

- Code: branch `ruoshi/feat-prompt-environment` (`f1f89f4`, not merged). Four
  edits to `agent/prompts/system.md`, all general: survey the environment
  first; install established tools rather than reimplement; check the network
  instead of assuming there is none; never print raw data to read by eye.
- Results: `eval/results/prompt-environment.csv`

| | Current prompt | New prompt |
|---|---|---|
| TB score | **0.8571** | 0.8095 |
| Total tokens | **1,442,339** | 1,551,816 (+8%) |
| Leaderboard score | **0.8427** | 0.7940 |

**Negative result — not merging.** The score gap is one trial
(polyglot-c-py 2/3), so this is "no evidence of improvement" rather than
"worse". Behaviour barely moved:

| Behaviour, across 21 trials | Current | New |
|---|---|---|
| Checked the network | 11 | 14 |
| `apt` install | 9 | 12 |
| Put a >5k-character output into the conversation | 6 | 5 |

The rule that mattered most, don't dump raw data, was mostly ignored:
chess-best-move still dumped pixel data in 3/3 trials, every one hitting the
6,000-character observation cap. One trial installed a chess engine for the
first time, then still couldn't read the board and timed out.

**Correction to the chess-best-move diagnosis above.** It blamed the starter
prompt's "there is no network" line for the agent never installing tools. The
old prompt still produced 9 `apt` installs on other tasks, so the model mostly
ignores that line; it isn't the main cause.

**Lesson: principles in the prompt change behaviour weakly.** To actually
change what the agent does, enforce it in code. Candidates, both general:

- Run a fixed environment probe (network, package managers, top-level
  directories) from the agent code before the first turn and put the result in
  the first message, instead of hoping the model thinks to look.
- Detect binary- or matrix-like command output and replace it with a short
  summary, instead of asking the model not to print it.

## 2026-10-04 — Why chess-best-move never passes (plan Phase 2 #5)

Diagnosis from transcripts, no new run. 13 trials across five runs, 0 passes.

The task: read a chess position from `chess_board.png`, write every
mate-in-one for white to `/app/move.txt`. The grader wants exactly the set of
winning moves, nothing more or less.

| What the agent did | Trials |
|---|---|
| Rendered squares as ASCII art and read hundreds of lines back into context | most |
| `pip install python-chess` | 7 / 13 |
| Installed a chess engine | **0 / 13** |
| Used `apt` for anything | **0 / 13** |
| Looked for resources shipped in the image (a font file sits in `/fonts`) | **0 / 13** |
| Wrote `move.txt` at all | 2 / 13, both wrong |
| Timed out (15 min) / gave up after 4 empty turns | 7 / 4 |

One representative 33-turn trial: turns 3–10 dump pixel art into the
conversation, 12–24 try to read pieces off it, 25–33 hand-write mate detection.
Six of the 33 turns were truncated mid-thought.

**Why it fails.** The model is text-only and is trying to *look* at an image
through ASCII dumps, which it can't do accurately — both answers it did write
had the position wrong. Meanwhile it never surveyed the environment (the asset
the board was drawn from was on disk) and never installed an established tool
when the network allowed it, choosing to reimplement instead.

**What not to do.** Telling the prompt about fonts or chess engines is
task-specific hardcoding, which the rules forbid and the top-5 code review
checks for. It's also 1 task in 89.

**What generalises.** Three habits that likely cost us on other tasks too:

1. Not surveying the environment first: unusual directories, network access,
   available package managers.
2. Reimplementing a standard tool instead of installing it when it can.
3. Pulling large raw data — pixels, binaries, long dumps — into the context to
   read by eye, instead of processing it with code.

Rules allow adjusting strategy by task *category*, so these can go into the
system prompt as general principles. Queued as Phase 2 #6, measured on the
whole slice: the point is whether the other six tasks improve or regress and
what happens to tokens, not whether chess-best-move flips.

## 2026-10-04 — Loop guard removed (plan Phase 2 #2)

- Code: `main` at `88fc9d9` with `agent/loop_guard.py` unwired from the loop
  (branch `exp/no-loop-guard`, not merged). Default reasoning effort.
- Same slice, 3 trials each. Ran as 11 trials plus a 10-trial fill after the
  first run was cut off; both halves used identical code.
- Results: `eval/results/no-loop-guard.csv`
- Compared against the 2026-09-30 run, which had the guard.

| | With guard | Without |
|---|---|---|
| TB score | 0.8571 | 0.8571 |
| Total tokens | **1,442,339** | 2,099,677 (+46%) |
| Leaderboard score | **0.8427** | 0.8361 |

**Keep it.** Identical tasks pass with and without it, so it doesn't touch
correctness — the jump from 0.57 to 0.86 was the truncation fix alone, which
settles the question the 09-30 entry left open. What the guard does is save
tokens, mostly on the tasks where the agent flails: chess-best-move (408k →
756k without it) and configure-git-webserver (228k → 450k).

Token spread is still large (chess-best-move varied by 834k across three
trials without the guard), so +46% is partly noise. The direction is
consistent and it costs no score.

## 2026-10-04 — Reasoning effort `medium` (plan Phase 2 #1)

- Code: `main` at `88fc9d9`, `LLM_REASONING_EFFORT=medium`, everything else
  as the 09-30 run
- Results: `eval/results/reasoning-effort-medium.csv`

| | Default (highest) | medium |
|---|---|---|
| TB score | **0.8571** | 0.7619 |
| Total tokens | 1,442,339 | **843,468** (−42%) |
| Leaderboard score | **0.8427** | 0.7535 |
| Wall clock | ~50m | 27m |

**Stay on the default.** medium cut tokens 42% but dropped
configure-git-webserver and sqlite-with-gcov from 3/3 to 2/3.

On 7 tasks the token penalty is tiny next to score: 600k tokens saved is worth
0.006 points, two lost trials cost 0.095. That changes at full scale, because
the penalty uses *total* tokens while the score is a mean. Extrapolating per-task
averages to all 89 tasks:

- default: 0.857 − 0.01 × 18.3 = **0.674**
- medium:  0.762 − 0.01 × 10.7 = **0.655**

Default still wins, by 0.02 instead of 0.09. Worth retesting once correctness
improves. The score gap is two trials out of 21, so some of it may be noise —
but nothing here suggests medium is better.

## 2026-09-30 — Truncated reasoning no longer stored (#8)

- Commit: `d6bf9a4` · Same slice, same 3 trials, same model as the baseline
- **Two changes, not one.** PR #8 shipped both the truncation fix and
  `agent/loop_guard.py` (repeat detection, stop after 8 consecutive failures).
  The loop guard rode along uncommitted from another branch and isn't in that
  PR's description, so the numbers below are the pair together. Measured alone
  on the old code the loop guard was worse, so the truncation fix is almost
  certainly doing the work — but "almost certainly" is not measured. A/B on
  removing the guard is queued behind the reasoning-effort experiment.
- Results: `eval/results/after-truncation-fix.csv`

| | Baseline | After #8 | |
|---|---|---|---|
| TB score | 0.5714 | **0.8571** | +50% |
| Total tokens | 3,104,345 | **1,442,339** | −54% |
| Leaderboard score | 0.5404 | **0.8427** | +56% |
| Wall clock | 2h 15m | ~50m | −63% |

Six of seven tasks now pass all three trials. polyglot-c-py went from 0/3 at
873k tokens to 3/3 at 153k. Only chess-best-move still fails.

### What we learned

**The timeouts were a context bug, not a capability limit.** Every baseline
failure was the model running out of time. It wasn't thinking too slowly — it
was re-reading 29k characters of its own unfinished thought on every turn. Same
model, same prompt, same tasks: fixing what we stored took the score from 0.57
to 0.86.

**Fixing the context also made everything cheaper and faster**, because input
tokens dominate the bill and re-sent garbage was most of them.

**The new no-action stop fired twice**, both on chess-best-move. That task now
gives up deliberately instead of burning its budget to a timeout.

**Spread is still wide.** configure-git-webserver passed 3/3 but its token
count varied by 349k. Treat any change smaller than that as noise.

### Next

1. Reasoning effort (#9) — we still run at the gateway default, the highest
   setting. That's the cause of the truncation #8 works around
2. chess-best-move — the one task we never solve
3. LangGraph port, once the numbers stop moving from cheap fixes

## 2026-09-24 — Baseline, unmodified starter agent

- Commit: `4ef6939` · Model: qwen3.8-27b (BadgerBrain) · Tasks: 7-task dev slice, 3 trials each
- Results: `eval/results/baseline.csv`

| | |
|---|---|
| TB score | **0.5714** |
| Total tokens | **3,104,345** |
| Leaderboard score | **0.5404** |
| Runtime | 2h 15m, 3 concurrent |

| task | pass | avg tokens | avg turns |
|---|---|---|---|
| log-summary-date-ranges | 3/3 | 29,893 | 8 |
| sqlite-with-gcov | 3/3 | 255,283 | 35 |
| fix-code-vulnerability | 3/3 | 279,763 | 29 |
| configure-git-webserver | 2/3 | 152,541 | 20 |
| regex-log | 1/3 | 727,835 | 21 |
| chess-best-move | 0/3 | 785,618 | 26 |
| polyglot-c-py | 0/3 | 873,412 | 22 |

### What we learned

**Every failure is a timeout, not a wrong answer.** All 7 failing trials ended
in AgentTimeoutError. The agent doesn't get the answer wrong; it runs out of
time still trying.

**Token spend predicts failure, inverted.** Tasks it solves cost 30k–280k
tokens; the two it never solves cost 785k and 873k. Burning tokens means stuck
in a loop, not working hard. So the lever isn't a smarter model — it's noticing
when it's stuck.

**One trial tells you nothing.** regex-log returned 1.0, 0.0 and a timeout
across three trials, with tokens from 50k to 460k. Compare changes on at least
3 trials, and treat differences smaller than the spread as noise.

**Input tokens dominate** — 90%+ of spend. The loop re-sends the whole
conversation every turn, so turn 30 pays for turns 1–29 again.

### Next

1. Loop detection — bail out or change approach after repeated failing commands
2. Turn cap well below the current 100 (nothing succeeded past 35 turns)
3. Context trimming — drop or summarize old command output

### Note on the first attempt

An earlier run of the same slice (2026-09-23) lost 16 of 21 trials to
APITimeoutError and took 18h37m. Cause was network drops with no retry in the
client; fixed in #5. Don't compare against those numbers.
