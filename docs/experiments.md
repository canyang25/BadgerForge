# Experiment log

Newest first. One entry per run we want to remember: what changed, what the
numbers were, what we learned. Numbers come from `scripts/score.py`.

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
