# Writeup draft (Kaggle, due Wed 2 Dec 2026, 23:59 Madison time)

Working draft of our Kaggle Writeup. Limit: title, subtitle and report,
2,500 words. Structure follows the organizers' `WRITEUP_TEMPLATE.md`; the
card fields follow the competition page. `TODO` marks what isn't decided
yet. Details for every number are in `docs/experiments.md`.

---

**Title:** BadgerForge: what a small ReAct agent on Qwen3.8-27B learned from full-benchmark failures *(TODO: shorten)*

**Subtitle:** Fixing how the agent handles cut-off and command-less replies took us from 0.438 to about 0.55 on Terminal-Bench 2.1; most other ideas measured as noise.

## Submission card

| Field | Value |
|---|---|
| code_url | TODO: `https://github.com/canyang25/BadgerForge/tree/<tag>` at the commit of the submitted run |
| scaffold | ReAct loop, one bash command per turn; nudges for command-less replies; cut-off reasoning kept only as a short tail; loop guard for repeats |
| model | `Qwen/Qwen3.8-27B-FP8` (served by UW BadgerBrain as `qwen3.8-27b`) |
| quantization | FP8 |
| reported_vram | 37.2 GB (`starter/scripts/estimate_vram.py`) |
| tb_score | TODO: from the submitted run |
| total_tokens | TODO: from the submitted run |
| leaderboard_score | TODO: five decimals |
| gpu | TODO: one dedicated GPU of the UW BadgerBrain gateway; ask the organizers which model |
| mean_wallclock_per_task | TODO |

The submitted run is decided in advance: the last full run on the final
commit, whatever it scores. The report lists every full run.

## 1. Summary

TODO (3–5 sentences). Points to make:
- Starter ReAct loop, kept simple; no new tools or multi-agent setup.
- Biggest gains came from reading full-run failures: replies cut off at the
  output limit, and replies that describe a step without running it.
- Full runs 3–7 (three agent versions, none measurably different): 52, 44,
  49, 54 and 47 of 89, mean 49.2/89 (0.553).
- Most later ideas (self-checks, sampling settings, never giving up) changed
  nothing measurable, and runs differ by about 4 tasks on their own.

## 2. Architecture

One task, start to finish (draft bullets; turn into prose):
- **Start:** wait for any apt/dpkg the image left running, then a system
  prompt with the rules and the task text.
- **Each turn (at most 100):** send the whole conversation to the model
  (reasoning effort medium, 16,384 output tokens, temperature 0.2, retries
  on gateway errors).
- **Parse the reply:** a bash block runs in the container (60 s limit; output
  over 6,000 characters keeps its head and tail); `TASK_COMPLETE` ends the task.
- **No command:** if the reply was cut off at the limit, keep only the last
  2,000 characters of its reasoning and send a generic nudge. Otherwise
  (announces a step, or empty) send a nudge that asks for the command itself
  and sample the next reply at 0.7. Four command-less turns in a row: give up.
- **Loop guard:** warn on a repeated command, refuse it after 3 repeats, stop
  after 8 failing commands in a row.
- **Serving:** the shared UW BadgerBrain gateway, concurrency 2, on a Windows
  laptop running Harbor in WSL2.

## 3. What we tried

In order, one line each (TODO: trim to fit the word limit):

| Change | Result |
|---|---|
| Starter agent, 7-task dev slice | 0.57; every failure a timeout |
| Store only the tail of cut-off reasoning instead of all of it | 0.86 on the slice, half the tokens |
| Retries on gateway errors; loop guard | kept: same score, fewer tokens |
| System prompt rewrite; environment probe; lower effort after a cut-off | no gain |
| **First full run** | 0.438 (39/89); half the failures were the agent giving up |
| New 10-task slice from tasks that pass only sometimes | baseline 0.40 |
| Nudge that asks for the command, hotter next sample | short-reply give-ups gone |
| Output limit 8k → 16k | cut-off give-ups halved; **full run 2: 0.539** |
| Reasoning effort medium | timeouts 20 → 10, wrong answers 5 → 15; **full run 3: 0.584** |
| Check before finishing, then a requirement-by-requirement checklist | no gain: the model's own checks are looser than the graders' |
| Model-card sampling (1.0 / 0.95 / 20) | no gain, slower |
| Never give up | no gain: trials it kept alive all ran out the clock |
| Three ways of handling a cut-off reply | no difference; cut-offs had become rare |
| Failure stop as a reminder | changed no outcome |
| Parser: matching code fences, `TASK_COMPLETE` on its own line | kept; **full run 6: 0.607** |
| Never run commands from cut-off reasoning | no gain: 10/30 vs 14/30; full run 7: 0.528 |

Analysis without runs: the system prompt's "no network" line didn't stop
installs; turn time is spent on output, not input, so compacting history
wouldn't help.

## 4. Results

- TODO: the submitted run's numbers, command and job name.
- Full runs 3–7: 52, 44, 49, 54, 47 (mean 49.2/89, standard deviation 4,
  close to what a single run's randomness predicts). 35 tasks passed in all
  five, 27 in none, 27 go either way.
- Full run 6, the best: 54/89, 0.60674 (wrong 14, timeouts 11, gave up 6,
  turn cap 4), main at `925566b`.
- TODO: per-category pattern, if we look at one.

## 5. Failure analysis

Draft from the 10-20 analysis of the 24 tasks we solve only sometimes:
- **Confident wrong answers:** 56 of 85 failures. In 53 of them the agent had
  checked something, just not what the task required. Examples: query-optimize
  never timed its query against the speed threshold; mteb-leaderboard ignored
  the task's date cut-off; sqlite-with-gcov set PATH only in its own shell.
- **Stuck on one approach:** build-pov-ray spent 54 of 100 commands on one
  download mirror.
- **Prose run as a command:** the parser could run the text between two code
  blocks; 79 times in 18,368 recorded replies (Preston's parser fix).
- TODO: pick 2–3 and write them up properly.

## 6. Borrowed and built

- MLM26 starter code: the ReAct loop and Harbor integration we started from.
- mini-swe-agent (MIT): compared prompt and loop; tested its cut-off nudge
  wording (no gain).
- Badger Agents' published numbers as a reference point.
- Qwen3.8-27B model card for the sampling experiment.
- Ours: evaluation tooling (scoring, per-trial export, Windows/WSL runner,
  resume fixes), the cut-off and command-less handling, and the experiment log.

## 7. Limitations and next steps

- Self-checks don't catch wrong answers; a check would need to run the
  deliverable the way the grader does.
- Run-to-run noise (about ±4 tasks) hides small improvements; we could only
  afford one trial per task on full runs.
- One shared gateway GPU: turn speed varies with load and time of day.
- Next: progress checks that switch approach when stuck; write the
  deliverable as soon as there is a plausible answer.

## 8. Team contributions

TODO: each of us writes our own line.
