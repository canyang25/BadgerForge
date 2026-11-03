# Writeup draft (Kaggle, due Wed 2 Dec 2026, 23:59 Madison time)

Working draft of our Kaggle Writeup. Limit: title, subtitle and report,
2,500 words. Structure follows the organizers' `WRITEUP_TEMPLATE.md`; the
card fields follow the competition page. `TODO` marks what isn't decided
yet. Details for every number are in `docs/experiments.md`.

---

**Title:** BadgerForge: learning from full-benchmark failures with a small ReAct agent

**Subtitle:** Fixing how the agent handles cut-off and command-less replies took us from 0.438 to between 0.49 and 0.61 on Terminal-Bench 2.1; most other ideas measured as noise.

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

TODO before submitting: cover image (a `harbor view jobs` screenshot). The
leaderboard score follows the competition page, not the older formula in
`WRITEUP_TEMPLATE.md`: TB score − min(0.01, 0.01 × (total tokens / 89) / 100,000,000).

## 1. Summary

BadgerForge is a small ReAct agent on Qwen3.8-27B: each turn the model writes
one bash command, the scaffold runs it, and the output comes back as the next
message. Our gains came from reading full-benchmark failures and fixing what
happens to replies that are cut off at the output limit or that describe a step
without running it, together with a larger output budget and medium reasoning
effort. Scores rose from 0.438 on the first full run to between 0.494 and 0.607
on runs 3–7. Most later ideas, including self-checks, other sampling settings
and never giving up, changed nothing we could measure, and one agent scored 52,
44 and 49 of 89 on three runs. TODO: final TB score, total tokens and
leaderboard score from the submitted run.

## 2. Architecture

**Model and serving.** We use `Qwen/Qwen3.8-27B-FP8` through the UW BadgerBrain
gateway, at reasoning effort medium, temperature 0.2 and 16,384 output tokens
per reply. Harbor runs in WSL2 on a Windows laptop at concurrency 2.

**Start.** Setup waits up to 120 s for any apt or dpkg process the image left
running. The first request holds a system prompt with the rules and the task
text.

**Each turn, at most 100.** The whole conversation goes to the model, with
retries on gateway errors. We don't compact history. On the tasks we checked,
generation took more of a turn than input did, so compaction wouldn't speed
turns up much, though it could still save input tokens.

**Parsing.** The first complete fenced shell block runs in the container with a
60 s limit. Stdout and stderr each keep their head and tail when over 6,000
characters. Without a shell block, a line holding only `TASK_COMPLETE` ends the
task.

**Cut-off and empty replies.** A reply cut off at the output limit is reduced to
its last 2,000 characters, and a reply with empty content is replaced by the last
2,000 characters of its reasoning. That text goes into the history and is parsed
like any other reply, so a command in it runs.

**Replies without a command.** The agent nudges only when it finds no action:
a generic nudge after a cut-off; otherwise a nudge asking for the command itself,
with the next reply sampled at temperature 0.7. Four such replies in a row end
the task.

**Loop guard.** A repeated command gets a warning and is refused after 3
repeats; 8 failing commands in a row end the task.

## 3. What we tried

We tested changes on 10–13 tasks with 3 trials each, ran both arms on the same
day, and for the later runs set the bar for a result in advance. Pass counts
alone were too noisy, so we also counted whether a change fired and what followed, and replayed
recorded replies offline before merging parser changes.

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
| LangGraph port, optional nodes off | no big drop; **full run 8: 0.517** |

Analysis without runs: the system prompt's "no network" line didn't stop
installs; on the tasks we checked, generation took more of a turn than input,
so compacting history wouldn't speed turns up much. We didn't test compaction
itself.

## 4. Results

- TODO: the submitted run's numbers, command and job name.
- Full runs 3–5, one agent (run 5 added a failure-stop switch that changed no
  outcome): 52, 44 and 49 of 89.
- Full run 6, main at `925566b` with the parser fixes: 54/89, 0.60674 (wrong 14,
  timeouts 11, gave up 6, turn cap 4). Main has this one run so far.
- Full run 7, main plus a change we didn't merge: 47/89, 0.52809.
- Full run 8, LangGraph port with optional nodes off: 46/89, 0.51685.
- Runs 3–7 span three agent versions, so their mean, 49.2/89 (0.553), describes
  those experiments and isn't a stable score for main. Across them 35 tasks
  passed in all five, 27 in none, 27 went either way.

## 5. Failure analysis

A 10-20 analysis of the 24 tasks we then solved only sometimes, a different set
from the 27 in Results, counted 56 confident wrong answers among 85 failures at
main's settings. Failing and passing trials used about the same turns and time.
That doesn't settle the cause, but the cases below suggest that how the agent
verifies its work is an important problem.

**Declaring success on a check that proves nothing: break-filter-js-from-html.**
The task asks for a payload that gets past a filter and runs in a browser. In
one trial the agent wrote `<svg OnLoad=alert(1)>`, ran `python test_outputs.py`
and finished. That file only defines tests, so nothing ran. query-optimize
failed the same way, never timing its query against the task's speed threshold.
In 53 of the 56 wrong answers the agent had checked something, just not what the
task required. Two forced checks before finishing didn't help: the model's own
checks are looser than the graders' and re-confirm its first answer.

**Stuck on one approach: protein-assembly.** In one batch, three trials spent 73
to 88 turns searching RCSB and PDB until the time limit and never started the
gBlock the task asks for. The search began going in circles before the first
empty reply, so the empty replies were a symptom. build-pov-ray looks similar,
with 54 of 100 commands on one download mirror.

**Breaking its own environment: adaptive-rejection-sampler.** Installing R hit
the 60 s command limit twice, so the agent ran `kill -9` on apt and dpkg. That
left dpkg broken, the verifier couldn't install curl, and no test ran. In another
run build-pov-ray ran `kill -9 -1` and took down its own container.

## 6. Borrowed and built

- MLM26 starter code: the ReAct loop and Harbor integration we started from.
- mini-swe-agent (MIT): compared prompt and loop; tested its cut-off nudge
  wording (no gain).
- Badger Agents' published numbers as a reference point.
- Qwen3.8-27B model card for the sampling experiment.
- LangGraph for the port on our branch.
- Ours: evaluation tooling (scoring, per-trial export, Windows/WSL runner,
  resume fixes), the cut-off and command-less handling, and the experiment log.

## 7. Limitations and next steps

- Self-checks don't catch wrong answers. A useful check would need to run the
  deliverable the way the grader does.
- Run-to-run noise of about 4 tasks hides small improvements, and we could only
  afford one trial per task on full runs.
- One shared gateway GPU: turn speed varies with load and time of day.
- WSL's clock drifted, so real time limits were 0.91 to 1.05 of nominal across
  runs, with no visible link to score. We don't know why. TODO: give the
  submitted run's value.
- A block inside a kept reasoning tail can still run. Stopping that removed
  those failed commands but showed no gain, so we left it.
- A LangGraph port with optional progress-check, early-deliverable and
  output-shaping nodes exists on a branch. The port alone showed no big drop, but
  the nodes are untested at benchmark scale.

## 8. Team contributions

TODO: each of us writes our own line.
