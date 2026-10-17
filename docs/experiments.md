# Experiment log

Newest first. One entry per run we want to remember: what changed, what the
numbers were, what we learned. Numbers come from `scripts/score.py`.

## 2026-10-17 — Full run 4: same agent as full run 3, 44/89

- Code: `ruoshi/fix-resume-job-name` (`0d9593b`); `agent/` identical to main
  `5c9fe4b`. Settings: code defaults (medium, 0.2, 16k, 4-strike give-up,
  100 turns, 60 s commands, apt wait) plus `LLM_BASE_URL` and `LLM_MODEL`.
- Started 10-16 10:12 CDT. The laptop blue-screened at 16:00 (NVIDIA driver
  `nvlddmkm.sys` 617.42); resumed 22:17, last trial 10-17 00:48, about 8.5 h
  of running. Results: `eval/results/full-run-4.csv`.

| | Full run 3 | Full run 4 |
|---|---|---|
| Passes | 52 | 44 |
| Wrong answers | 15 | 19 |
| Timeouts | 10 | 14 |
| Gave up | 7 | 6 |
| Hit the 100-turn cap | 3 | 4 |
| Verifier timeouts | 2 | 2 |
| Tokens per task | 476k | 565k |

TB 0.49438, leaderboard 0.49433. Gateway median 13 s/turn, no slow trials,
no connection failures.

**Same agent, 8 fewer passes: noise.** 11 tasks went pass → fail and 3 fail →
pass. Matched task by task, output per turn is unchanged (median ratio 1.03,
geometric mean 1.05; 29 tasks over 20% longer, 22 over 20% shorter), and
output tokens per second were 105–120 throughout, as in run 3. Two trials
(rstan-to-pystan, sam-cell-seg) were rerun because the crash interrupted
them; the 14 trials run after the restart passed 6, the same as those tasks
in run 3. Runs 2→3 flipped 24 tasks and runs 3→4 flipped 14, so one full run
is a rough number. **Estimate for this agent: 2 runs, 44 and 52, mean 48/89
(0.539).**

**The resume fix worked in a real interruption.** This job's config.json had
no `job_name`; resume pinned it and continued in the same directory, with
none of the 74 finished trials rerun. Setup took at most 0.5 s in all 89
trials, so the apt wait never fired.

## 2026-10-15 — Batch 2: what a cut-off reply leaves behind (#25): no

- From #24 (reading mini-swe-agent, 10-14): it drops a cut-off reply from the
  history and tells the model to answer concisely and think briefly; we keep
  the reply's last 2000 characters and a generic nudge.
- Code: `ruoshi/feat-cutoff-handling` (`d300d31`), not adopted:
  `AGENT_CUTOFF_HANDLING` = `tail` (as now), `concise` (tail plus the
  mini-swe-agent nudge) or `drop` (nudge only). Main otherwise.
- 13 tasks, 3 trials, three arms the same day: batch 1's set with
  feal-differential, mteb-leaderboard, mteb-retrieve and sqlite-with-gcov
  swapped for polyglot-rust-c, largest-eigenval, code-from-image and
  protein-assembly. Results: `eval/results/cutoff-tail.csv`,
  `cutoff-concise.csv`, `cutoff-drop.csv`.

| | tail | concise | drop |
|---|---|---|---|
| Passes | 18/39 | 19/39 | 21/39 |
| Wrong answers | 13 | 15 | 12 |
| Give-ups | 5 | 2 | 4 |
| Timeouts | 3 | 3 | 1 |
| Other errors | 0 | 0 | 1 |
| Cut-off turns | 19 | 11 | 22 |
| Median s/turn | 12.5 | 9.8 | 11.2 |
| Tokens per task | 408k | 427k | 506k |

No turn-cap hits; each column sums to 39. drop's error is build-pov-ray's
verifier not writing a reward file.

**No difference we can attribute to the setting.** Cut-offs are rare now:
5–9 trials per arm had any, 1–2% of all turns, and the setting only acts after
one. Trials with a cut-off passed 3/7, 1/5, 4/9; trials without passed 15/32,
18/34, 17/30, so two of drop's three extra passes came from trials the
setting never touched. The arms ran by day, early evening and night, which is
likely where the s/turn spread comes from. **Not adopted:** drop also costs
25% more tokens per task. 6 of the 11 give-ups had no cut-off at all, they
were command-less replies (#14); break-filter-js-from-html was 0/3 with 2
give-ups in every arm.

**Tooling.** One concise trial needed a rerun after its container didn't
start in time, and `harbor jobs resume` reran the whole arm: harbor had left
`job_name` out of config.json. Fixed in `run_full.sh resume` (#26).

## 2026-10-14 — Batch 1: model-card sampling (#20) and never giving up (#21): no

- Code: `ruoshi/feat-sampling` (`6867ff0`), not merged: optional `top_p`,
  `top_k`, `min_p`, `presence_penalty`. Otherwise main at the time (medium,
  16k, 0.2).
- 13 tasks, 3 trials, three arms the same day: break-filter-js-from-html,
  feal-differential-cryptanalysis, feal-linear-cryptanalysis,
  sqlite-db-truncate, build-pov-ray, mailman, build-cython-ext,
  configure-git-webserver, extract-elf, mteb-leaderboard, mteb-retrieve,
  sqlite-with-gcov, git-leak-recovery. Results: `eval/results/sampling-base.csv`,
  `sampling-card.csv`, `giveup-never.csv`.

| | Baseline | Card sampling (1.0 / 0.95 / 20, min_p 0) | Never give up |
|---|---|---|---|
| Passes | **18/39** | 17/39 | 13/39 |
| Wrong answers | 13 | 13 | 15 |
| Hit the 100-turn cap | 2 | 3 | 2 |
| Give-ups | 5 | 4 | 0 |
| Timeouts | 1 | 1 | 9 |
| Verifier timeouts | 0 | 1 | 0 |
| Cut-off turns | 21 | 29 | 46 |
| Replies without a command | 55 | 18 | 123 |
| Median s/turn | 7.9 | 9.9 | 8.0 |
| Tokens per task | 489k | 581k | 518k |

Wrong answers here exclude the turn cap; the CSVs' `wrong_answer` includes it
(15 / 16 / 17). Each column sums to 39.

**Card sampling doesn't carry over to our loop.** Far fewer replies without a
command, but no more passes, 25% slower turns, 19% more tokens and more
cut-offs. top_k really is applied: at temperature 2.0 with `top_k=1` three
answers were identical, without it all three differed. One card-arm trial
hit a verifier timeout on mteb-retrieve, which is 0/3 in every arm.

**The 4-strike give-up rule is right.** Never giving up kept 5 trials past
their 4th command-less turn in a row; none recovered, all ran until timeout
(1,203–1,805 s). The three feal-differential ones had given up after 417–744 s
in the baseline. The arm's 5 fewer passes are noise: mailman −2,
sqlite-db-truncate −2, feal-linear −1, break-filter −1, extract-elf +1, all in
trials the setting never touched (it's read only in the give-up check).
Giving up after 8 needs no run of its own: two of the five never went past
4–5 command-less turns in a row and would still have run out the clock; the
other three went 14–17 and would have stopped at 8 instead of 4.

**For the next batch:** 5 tasks gave the same result in every arm
(feal-differential, mteb-leaderboard, mteb-retrieve never; sqlite-with-gcov,
git-leak-recovery always). Swap them for tasks that go either way.

## 2026-10-13 — Analysis only: where the remaining points are

No new runs; full run 3's transcripts and every per-trial CSV (544 trials).

- **#17, the "no network" line, costs nothing.** No reply in full run 3 says
  it's offline. 33 of 89 trials installed or downloaded (199 commands); 1 hit
  a network error, a dead SourceForge mirror. Dropped.
- **Repetition isn't what loses tasks.** The loop guard's repeat warning fired
  in 17 of the 52 passes (47 times) and 13 of the 37 failures (29 times).
  Failures are cut-offs: 68 in the 7 give-ups and 76 in the 10 timeouts,
  against 11 across all 52 passes.
- **Where points can come from.** Of 89 tasks, 28 have always passed and 25
  never have; the other 36 go either way. Of full run 3's 20 give-ups,
  timeouts and turn-cap failures, only 5 have ever passed anywhere.
- **The 60 s command limit** killed 65 commands (32 in trials that passed):
  24 Python or training runs, 16 servers, sleeps or waits, 14 installs.
- **The dpkg lock at start-up** failed installs in six trials; now waited
  out in `setup()` (#23).
- **Time per turn is output, not input**, so compacting history (#18) wouldn't
  speed turns up.

## 2026-10-12 — Check before finishing (#16): no

- Code: `ruoshi/feat-verify-before-done` (`287849d`), not merged. With
  `AGENT_VERIFY_BEFORE_DONE=1` the first TASK_COMPLETE asks the model to
  confirm every requirement with commands; `AGENT_VERIFY_EFFORT` sets the
  effort for those turns. Everything at medium otherwise.
- 13 tasks that flipped between full runs 2 and 3 (6 that medium broke, 7 it
  fixed), 3 trials, three arms the same day. Results:
  `eval/results/verify-base.csv`, `verify-a.csv`, `verify-b.csv`.

| | No check | Check at medium (A) | Check at full effort (B) |
|---|---|---|---|
| Passes | 26/39 | 27/39 | 25/39 |
| The 6 medium broke | 8/18 | 8/18 | 8/18 |
| The 7 medium fixed | 18/21 | 19/21 | 17/21 |
| Median s/turn | 8.5 | 6.8 | 9.3 |

**The check doesn't help.** It started in 74 of 78 trials, but most checks
re-listed files, re-ran the agent's own test and said TASK_COMPLETE again.
On the six, four checks changed something: one real fix (B, build-cython-ext:
found `np.int` and recompiled), and two or three breakages (A, extract-elf:
shifted correct addresses by 0x400000; A and B, configure-git-webserver:
"cleaned up" a working repo and rebuilt it). configure-git-webserver went
3/3 → 2/3 → 1/3. No check caused a timeout.

**Full run 3 overstated what medium costs.** On the six it broke, single
trials said 0/6; three trials say 8/18. Medium does get more wrong, but less
than one run suggested, and the seven it gained hold at 18/21.

**Tooling.** The gateway was down 10:33–13:30, first refusing connections,
then answering 502. `run_full.sh resume` doesn't treat 502s as gateway
failures, so those trials were rerun by hand. Plan #19.

## 2026-10-12 — Medium reasoning effort (#13): slice and full run 3

- Code: `main` at `d90d2b9` (act nudge, 16k) with `LLM_REASONING_EFFORT=medium`.
  Slice: 3 trials. Full run: one trial per task, 7 h 51 min, no resumes.
- Results: `eval/results/slice-medium.csv`, `eval/results/full-run-3.csv`

| | Slice, default (highest) | Slice, medium | Full run 2, default | Full run 3, medium |
|---|---|---|---|---|
| Passes | 19/30 | 18/30 | 48/89 | **52/89** |
| Timeouts | 6 | 3 | 20 | 10 |
| Wrong answers | 2 | 5 | 5 | 15 |
| Gave up | 3 | 3 | 11 | 7 |
| Median s/turn | 46 | 15 | 27.7 | 12.2 |
| Output tokens per turn | 4,565 | 1,608 | 2,647 | 772 |
| Tokens per task | 302k | 270k | 580k | 476k |

Full run 3: TB 0.58427, leaderboard 0.58422. One slice trial failed because
its environment never started.

**Medium wins at full scale and is a wash on the slice.** It trades depth for
speed. 7 of full run 2's 20 timeouts now pass (adaptive-rejection-sampler,
cobol-modernization, db-wal-recovery, financial-document-processor,
largest-eigenval, overfull-hbox, password-recovery). Wrong answers tripled,
and six full-run-2 passes became wrong answers: build-cython-ext,
configure-git-webserver, extract-elf, mteb-leaderboard, mteb-retrieve,
sqlite-with-gcov. The slice has few time-bound tasks, so it couldn't show the
gain.

**How sure we are.** 14 tasks flipped to pass and 10 to fail, so +4 is within
what a single run can swing. It's the default anyway: it isn't worse, turns
are 2–3× faster, a full run takes 8 h instead of 11, and tokens per task fell
18%. This reverses the 10-05 result on the old slice.

**What's left.** Wrong answers (15) are now the largest failure: plan #16.
Seven tasks still time out at 12 s/turn: #15. Give-ups are cut-offs and empty
answers only, no short replies: #14.

## 2026-10-11 — Full run 2: act nudge + 16k

- Code: `ruoshi/feat-max-tokens-16k` (`61a99aa`), i.e. #22's act nudge and
  16k output tokens. Same laptop, concurrency 2, one trial per task. The VPN
  was down 16:52–19:27; four trials that failed on the gateway were rerun on
  resume.
- Results: `eval/results/full-run-2.csv`. Gateway median 28 s/turn.

| | Full run 1 (10-07) | Full run 2 |
|---|---|---|
| TB score | 0.43820 (39/89) | **0.53933** (48/89) |
| Tokens per task | 587k | 580k |
| Leaderboard score | 0.43814 | **0.53927** |
| Gave up | 25 | 11 |
| Timeout | 9 | 20 |
| 100-turn cap | 6 | 3 |
| Wrong answer | 7 | 5 |
| Verifier timeout | 3 | 2 |

**+9 tasks, from fewer give-ups.** 16 tasks flipped to pass: 10 had given up
in run 1, 3 had hit the turn cap, 2 were wrong answers, 1 a verifier timeout.
7 flipped to fail, 6 of them timeouts: cobol-modernization, db-wal-recovery,
financial-document-processor, mailman, overfull-hbox, path-tracing. mailman
timed out as the VPN dropped, so that one may not be the agent.

**Timeouts are now the biggest failure, and the time goes to thinking.** 20
timeouts, at roughly 30 s per turn and 2–9k output tokens per turn. The
per-trial median rose to 27.7 s/turn from 18.7. The slice showed the same
trade (6 timeouts at 16k against 2).

**Empty answers are in 10 of the 11 give-ups.** Of the last four replies of
each give-up: 21 cut off, 19 empty answers, 4 short. Plan #14.

## 2026-10-09 — 16k on top of the act nudge (#12 again)

- Code: `ruoshi/feat-act-nudge` (`15b2523`) with `LLM_MAX_TOKENS=16384`.
  Slice, 3 trials, Windows box, concurrency 2, 3 h 38 min.
- Results: `eval/results/slice-act16k.csv`

| | Act nudge, 8k | Act nudge, 16k |
|---|---|---|
| Passes | 14/30 | **19/30** |
| Give-ups (all cut-off streaks) | 8 | 3 |
| Timeouts | 2 | 6 |
| Tokens per task | 397k | 302k |
| Median s/turn | 26 | 46 |

**16k is worth it.** Both 16k runs beat both 8k runs on the slice (16 and 19
passes against 12 and 14), and cut-off give-ups fell to 3 from 8.
feal-linear-cryptanalysis passed for the first time in any run (1/3). 16384
is now the default.

**The cost is time.** Turns took 46 s against 26 s, mostly on the
heavy-thinking tasks (write-compressor 106 vs 46 s/turn, feal 79 vs 37).
Timeouts rose to 6 from 2: all three largest-eigenval trials hit their 900 s
limit after 12–22 turns. Gateway speed also varies by day, so not all of the
slowdown is ours. A full run will show whether the trade holds on long tasks.

**Half the command-less replies at 16k are empty answers.** 14 of 29 had no
content, only reasoning, yet the finish reason wasn't `length`. The agent
treats them like narration (act nudge, 0.7) and 9 of 12 were followed by a
command, so that works, but llm.py labels them "cut off — you spent the whole
output budget", which isn't true. Plan #14.

## 2026-10-09 — New slice: 16k output budget, and the act nudge (#11, #12)

Both on the 10-task slice, 3 trials each, Windows box, concurrency 2.
Results: `eval/results/slice-maxtok16k.csv`, `eval/results/slice-actnudge.csv`.

| | Baseline (8k) | `LLM_MAX_TOKENS=16384` | Act nudge, 8k |
|---|---|---|---|
| Passes | 12/30 | 16/30 | 14/30 |
| Give-ups | 12 | 7 | 8 |
| …on short replies | 2 in the full-run trial (rest not classified) | 3 | **0** |
| …on cut-off streaks | — | 4 | 8 |
| Tokens per task | 311k | 311k | 397k |
| Gateway median | 19–29 s/turn | 38 s/turn | 26 s/turn |

**The act nudge does what it's for.** A reply that ends without a command and
wasn't cut off now gets a nudge that asks for the command itself, and the next
request runs at temperature 0.7. 22 such replies across the 30 trials, nearly
all on turn 1; 18 were followed by a command (82%; 65% at 8k before, 43% in
the 16k run). No trial gave up on short replies, and modernize-scientific-stack
and portfolio-optimization went 6/6. Merging it.

**Passes didn't move beyond noise.** regex-log fell to 1/3 on two cut-off
streaks, a path this change doesn't touch (cut-off turns keep the old nudge
and temperature); it was 3/3 and 2/3 in the other runs. On 10 tasks × 3
trials, ±2 passes is noise, so judge changes by the failure they target too.

**16k halves cut-off give-ups but doesn't break thinking loops.** 4 cut-off
give-ups at 16k against 8 at 8k in the act-nudge run; sqlite-db-truncate went
3/3 (1/3 in both 8k runs). feal-linear-cryptanalysis still gave up in all
three trials, after 4 × 16,384 tokens of thinking with no command. Turns were
~8% slower where the budget was used, tokens per task unchanged. Correction to
our 10-08 read: reshard-c4-data's 3/3 at 16k repeated at 8k in the act-nudge
run, so that one wasn't the budget.

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
