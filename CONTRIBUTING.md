# Contributing to BadgerForge

Four people, four coding agents. These rules keep `main` something a human can still read.

## The short version

1. Never push to `main`. Everything lands through a PR.
2. One PR = one change, under ~400 changed lines.
3. Someone other than the author approves it.
4. You own every line your agent writes. Read the whole diff before asking for review.
5. Claim files before editing them (see [Avoiding collisions](#avoiding-collisions)).

## Branches

`<name>/<type>-<topic>`, lowercase, hyphens.

- `name`: your first name (`ruoshi`, `andrew`, …)
- `type`: `feat`, `fix`, `eval`, `docs`, `chore`
- Example: `ruoshi/feat-context-trimming`

Branches are short-lived. Delete after merge. If a branch is older than a week, rebase it or close it.

## Pull requests

**Size.** Aim for under 400 changed lines, not counting lockfiles or data. If your agent produced more, split it: refactor first, behavior change second. A reviewer should finish in 15 minutes.

**Scope.** One concern per PR. "Add planner node" and "rename state fields" are two PRs.

**Description.** Three things, a few lines each:
- What changed and why
- How you tested it (unit tests, and which tasks you ran)
- For anything that changes agent behavior: score and total tokens before/after on the same task subset. Tokens cost us points, so a change that raises score and doubles tokens needs a word of justification.

**Review.** Any teammate other than the author approves. Rotate so everyone learns every part of the code. Reviewers check logic and intent; don't hand-audit formatting (tooling does that). If you're asked to review, respond within a day.

**Merge.** Squash merge, by the author, after approval and green checks. Draft PRs are for work in progress.

## What an agent may do

**Without asking**, inside the files your PR claimed:
- Edit and add code and tests
- Run the test suite, lint, and Harbor runs locally

**Ask a human on the team first** (post in the chat):
- Adding or upgrading dependencies (`pyproject.toml`, `uv.lock`)
- Changing shared contracts: the graph state schema, `agent/llm.py`, the system prompt
- Creating new top-level directories or moving files
- Deleting files it didn't create
- CI config, `.gitignore`, repo settings

**Never:**
- Push to `main`, force-push someone else's branch, or merge its own PR
- Commit secrets. BadgerBrain keys live in 1Password. `.env.op` holds only `op://` references and is loaded with `op run --env-file=.env.op --`. No plain `.env` anywhere in the repo
- Commit `jobs/` output, model weights, or large data
- Use closed-weight models anywhere in the agent (competition rule)

## Avoiding collisions

Two agents rewriting the same file on two branches is the most expensive mistake we can make.

1. **Claim before you start.** Open a draft PR (or a GitHub issue assigned to you) listing the files or directories you'll touch. Check open PRs first.
2. **Hot files need a heads-up.** `agent/state.py`, `agent/llm.py`, and `agent/prompts/system.md` are touched by everything. Announce in chat, keep those edits small, and merge them fast so others can rebase.
3. **Stay in your lane.** Tell your agent which files it may edit. If it wants to change something outside the claim, stop and coordinate.
4. **Rebase on `main` daily** and before requesting review.

## Commit messages

```
type(scope): imperative summary under 72 chars

Why this change, if it isn't obvious. Eval numbers if behavior changed.
```

- `type` matches branch types; `scope` is the area (`graph`, `tools`, `eval`, …)
- Example: `fix(tools): truncate command output to 4k chars`
- Commits can be messy on your branch; the squash-merge title is what `main` keeps, so make that one good.

## Repo layout

```
plan.md             Current plan: goal, ordered steps, how we know each works
agent/              Harbor agent package (entry point: agent/agent.py)
  graph/            LangGraph nodes and edges, one node per file
  state.py          Graph state schema (hot file)
  llm.py            Model client (hot file)
  tools/            Actions the model can take in the container
  prompts/          Prompt text as .md files, not strings in Python
tests/              Unit tests, mirror agent/ paths, no Docker or model calls
eval/
  subsets/          Task lists (*.txt) we benchmark on
  results/          Small summary CSVs we want to keep (score, tokens, commit)
scripts/            Run and analysis scripts
docs/               Design notes and experiment log
.env.op             op:// references only, safe to commit
jobs/, .env         Gitignored
```

`agent/state.py` and all tool inputs/outputs are Pydantic models. Parse model output into one before acting on it, so bad output fails loudly instead of reaching the container.

Where does a new file go?

- Changes how the agent decides → `agent/graph/`
- Something the agent can do in the container → `agent/tools/`
- Words sent to the model → `agent/prompts/`
- Runs or measures the agent → `scripts/` or `eval/`
- Changes what we're building or in what order → `plan.md` (update it before writing the code)
- Explains a decision → `docs/`
- None of these → ask before creating a new directory.
