# Experiment log

Newest first. One entry per run we want to remember: what changed, what the
numbers were, what we learned. Numbers come from `scripts/score.py`.

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
