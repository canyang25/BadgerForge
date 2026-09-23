# Plan: Minimum Viable Pipeline

## Goal

Run an agent end to end on a small task slice and get a number we trust: score, tokens, leaderboard score. That number is the baseline every later change is A/B tested against.

Leaderboard score = `TB score − 0.01 × (total tokens / 1M)`. Tokens cost points, so we always report both.

## MVP

| | Choice | Why |
|---|---|---|
| Tasks | Dev slice: 7 tasks from `terminal-bench/terminal-bench-2-1` (below) | Small enough to rerun in under an hour |
| Model | Qwen on BadgerBrain | Approved anchor model, free, no GPU needed |
| Agent | Starter `BaselineAgent`, unchanged | Understand it before improving it |
| Score | Mean reward + total tokens from Harbor `result.json` files | Same numbers the leaderboard uses |

Benchmark is 89 tasks (2.1 revises 26 of the 2.0 tasks; the task list is the same size).

Dev slice: `chess-best-move`, `configure-git-webserver`, `fix-code-vulnerability`, `log-summary-date-ranges`, `polyglot-c-py`, `regex-log`, `sqlite-with-gcov`.

Left out of the slice: `build-cython-ext` (reference solution is broken, scores 0 every time) and `qemu-startup`, `qemu-alpine-ssh` (can't run on Apple Silicon).

## Steps

Each step is one PR. Don't start a step until the one before it is merged.

| # | Step | Done when | Owner |
|---|---|---|---|
| 1 | Copy starter agent into `agent/`, following CONTRIBUTING layout | `harbor run -d terminal-bench/terminal-bench-2-1 -a oracle -i regex-log` gives reward 1.0, and the baseline agent starts on `regex-log` from our repo | |
| 2 | Connect BadgerBrain via `.env.op` + `op run` | `regex-log` run finishes with non-zero input/output tokens in `result.json`, no key in any file | |
| 3 | `scripts/score.py`: job dir → score, tokens, leaderboard score, per-task table | Unit test on a saved `result.json` fixture passes | |
| 4 | Baseline run on the dev slice, 3 trials per task | `eval/results/baseline.csv` committed with score, tokens, commit SHA | |
| 5 | First improvement: parse model output into Pydantic models, retry on bad format | Parser unit tests pass; dev-slice score ≥ baseline, tokens not higher | |

LangGraph comes after step 5. Every change after that has to beat the step 4 numbers.

## Not in MVP

LangGraph rewrite, planning or self-verification nodes, custom tools, full 89-task runs.

## Open questions

- ~~TB 2.0 or 2.1?~~ Settled: **2.1** (confirmed with organizers 9/23). Note the challenge repo still says 2.0 everywhere, so the writeup should state which we used.
- Where do full runs happen? Needs x86 Linux (qemu tasks fail on Macs).
- 3 trials per task enough to see real differences, given BadgerBrain allows only 2-4 concurrent runs?
