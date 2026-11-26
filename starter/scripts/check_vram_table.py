#!/usr/bin/env python3
"""Sanity-check every reported VRAM number in the approved-model table against the Hub.

Usage (from the repo root):

    python starter/scripts/check_vram_table.py
    python starter/scripts/check_vram_table.py --tolerance 5

What this does
==============
The leaderboard's "reported VRAM" numbers live in the approved-model table in the challenge README.
Nobody should have to take those on faith, so this script re-derives each
one from public information and prints the two side by side:

1. Parse every checkpoint out of the README's approved-model table (the repo id in backticks and
   its "NN GB" reported VRAM).
2. For each row, rebuild the estimate from public information, using
   ``estimate_vram.py``:

       weights   — the published checkpoint's actual file sizes on the
                   HuggingFace Hub (so AWQ/GPTQ/FP8 checkpoints are
                   handled automatically; no parameter counting)
       KV cache  — for a 16k-token context at fp16, single batch,
                   computed from the model's config.json:
                   layers x KV heads x head_dim x 2 (K and V) x 2 bytes
       headroom  — a flat 2 GB for activations and runner overhead

3. Compare. Rows within ``--tolerance`` GB (default 4) pass. Larger gaps,
   or repos that can't be fetched, are flagged and the script exits
   nonzero — so it can also run in CI to keep the table honest.

How to read the output
======================
A small gap between table and estimate is expected: the table rounds up
a little, checkpoints get re-uploaded, and the KV term depends on config
details. A big gap means either the table row is wrong (tell the
organizers via the Kaggle Discussion tab) or the repo id points at a
different checkpoint than the table intended.

Notes
=====
- Needs network access to huggingface.co. No GPU, no model downloads —
  only two small JSON requests per model.
- The table value stays canonical for scoring either way. This script is
  for transparency: anyone can verify the numbers, and anyone proposing a
  new model can produce one the same way.
- Don't compare against nvidia-smi — most serving stacks preallocate a
  large memory pool at startup, so the reading reflects your GPU, not
  the model.
"""

import argparse
import re
import sys
import urllib.error
from pathlib import Path

# estimate_vram.py lives next to this file; make it importable no matter
# what directory the script is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import estimate_vram as ev  # noqa: E402

# This file lives at starter/scripts/, so the challenge README is two levels up.
TABLE_FILE = Path(__file__).resolve().parents[2] / "README.md"

# Matches an approved checkpoint entry and captures (repo id, VRAM number).
# The table lists each checkpoint as a backticked HuggingFace id followed by
# its reported VRAM in parentheses:
#   `Qwen/Qwen2.5-Coder-32B-Instruct-AWQ` (28 GB)
# The repo id must contain a "/" (owner/name), so non-Hub entries like
# Ollama tags (`qwen3-coder:30b`) are skipped — they can't be verified
# against the Hub API anyway.
ENTRY = re.compile(r"`([\w./-]+/[\w./-]+)`\s*\(([\d.]+)\s*GB\)")


def table_rows() -> list[tuple[str, float]]:
    """Return (repo_id, reported_vram_gb) for every Hub checkpoint in the approved-model table."""
    rows = list(dict.fromkeys(
        (repo, float(gb)) for repo, gb in ENTRY.findall(TABLE_FILE.read_text())
    ))
    if not rows:
        # Most likely the table format changed and the regex above needs
        # updating — better to fail loudly than to report "all good" on
        # an empty check.
        raise SystemExit(f"No model entries parsed from {TABLE_FILE} — did the table format change?")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tolerance", type=float, default=4.0,
        help="allowed |estimate - table| in GB before a row is flagged (default: 4)",
    )
    tol = parser.parse_args().tolerance

    failures = 0
    print(f"{'model':<48} {'table':>7} {'estimate':>9}  verdict")
    for repo, table_gb in table_rows():
        try:
            w = ev.weights_bytes(repo)          # bytes of the published checkpoint
            kv, _ = ev.kv_cache_bytes(repo)     # bytes of KV cache @ 16k, fp16
            est = w / 1e9 + kv / 1e9 + ev.OVERHEAD_GB
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, SystemExit) as e:
            # Repo id typo, gated/private repo, renamed checkpoint, or no
            # network. The row can't be verified, which is itself a finding.
            print(f"{repo:<48} {table_gb:>5.0f} G {'—':>9}  UNREACHABLE ({e})")
            failures += 1
            continue

        diff = est - table_gb
        ok = abs(diff) <= tol
        verdict = "ok" if ok else f"OFF BY {diff:+.1f} GB"
        print(f"{repo:<48} {table_gb:>5.0f} G {est:>7.1f} G  {verdict}")
        failures += 0 if ok else 1

    if failures:
        print(f"\n{failures} row(s) need attention.")
        raise SystemExit(1)
    print("\nAll rows within tolerance.")


if __name__ == "__main__":
    main()
