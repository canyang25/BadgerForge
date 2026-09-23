#!/usr/bin/env python3
"""Print score, tokens and leaderboard score for one or more Harbor job dirs.

    ./scripts/score.py jobs/2026-09-23__17-35-20 [more dirs...]
    ./scripts/score.py jobs/* --csv eval/results/baseline.csv
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.scoring import format_table, load_trials, summarize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_dirs", nargs="+", type=Path)
    parser.add_argument("--csv", type=Path, help="also append the per-task rows here")
    args = parser.parse_args()

    trials = [t for d in args.job_dirs for t in load_trials(d)]
    if not trials:
        print(f"No result.json found under: {', '.join(map(str, args.job_dirs))}")
        return 1

    summary = summarize(trials)
    print(format_table(summary))

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        new = not args.csv.exists()
        with args.csv.open("a", newline="") as fh:
            writer = csv.writer(fh)
            if new:
                writer.writerow(["task", "trials", "reward", "tokens", "token_spread"])
            for t in summary.tasks:
                writer.writerow(
                    [t.task, t.trials, f"{t.reward:.3f}", f"{t.tokens:.0f}", t.token_spread]
                )
        print(f"\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
