#!/usr/bin/env python3
"""Write one CSV row per trial, for picking a dev slice from a broad run.

    ./scripts/export_trials.py jobs/full-20261007-1900 --out eval/results/full-trials.csv

score.py averages per task. Choosing tasks for a slice needs more than that:
how a trial ended (passed, wrong answer, timed out, gave up, gateway failure),
how many turns and tokens it took, and how long. Small enough to commit, so a
run done on one machine can be analysed on another.
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

FIELDS = [
    "task", "trial_id", "reward", "outcome", "turns",
    "input_tokens", "output_tokens", "seconds", "exception", "stop_reason",
]


def _seconds(execution: dict) -> float | None:
    try:
        start = datetime.fromisoformat(execution["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(execution["finished_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None
    return round((end - start).total_seconds(), 1)


def outcome(reward, exception, stop_reason) -> str:
    if exception in ("APIConnectionError", "APITimeoutError"):
        return "gateway_failure"
    if reward == 1:
        return "pass"
    if exception == "AgentTimeoutError":
        return "timeout"
    if stop_reason == "no_action":
        return "gave_up"
    if exception:
        return "error"
    return "wrong_answer"


def rows(job_dirs):
    for job in job_dirs:
        for path in sorted(Path(job).rglob("result.json")):
            trial = path.parent.name
            if "__" not in trial or trial[:1].isdigit():  # job-level summary
                continue
            data = json.loads(path.read_text())
            agent = data.get("agent_result") or {}
            meta = agent.get("metadata") or {}
            reward = ((data.get("verifier_result") or {}).get("rewards") or {}).get("reward")
            exception = (data.get("exception_info") or {}).get("exception_type")
            stop = meta.get("stop_reason")
            yield {
                "task": trial.split("__")[0],
                "trial_id": trial,
                "reward": reward,
                "outcome": outcome(reward, exception, stop),
                "turns": meta.get("turns"),
                "input_tokens": agent.get("n_input_tokens"),
                "output_tokens": agent.get("n_output_tokens"),
                "seconds": _seconds(data.get("agent_execution") or {}),
                "exception": exception or "",
                "stop_reason": stop or "",
            }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_dirs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    found = list(rows(args.job_dirs))
    if not found:
        print("No trial result.json found.", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(found, key=lambda r: (r["task"], r["trial_id"])))

    counts = {}
    for r in found:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    print(f"wrote {len(found)} trials to {args.out}: "
          + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
