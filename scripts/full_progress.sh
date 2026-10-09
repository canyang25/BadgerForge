#!/usr/bin/env bash
# One line of progress for a full run, from inside WSL or any Linux box:
#
#   ./scripts/full_progress.sh                      newest jobs/full-*
#   ./scripts/full_progress.sh jobs/full-<timestamp>
#
# Counts trial result.json files (trial dirs are <task>__<id>; the job-level
# summary dir is skipped), so it works while harbor runs and after it died.
# "harbor" says whether the orchestrator process is alive — a tmux session
# can outlive it, so `tmux ls` is not a liveness check.
set -uo pipefail
cd "$(dirname "$0")/.."

JOB="${1:-$(ls -dt jobs/full-20* 2>/dev/null | head -n 1)}"
[ -n "$JOB" ] || { echo "no jobs/full-* yet" >&2; exit 1; }

done_n=0; pass=0
for f in "$JOB"/*/*__*/result.json "$JOB"/*__*/result.json; do
  [ -f "$f" ] || continue
  case "$(basename "$(dirname "$f")")" in [0-9]*) continue ;; esac   # harbor's own job dir
  done_n=$((done_n + 1))
  grep -q '"reward": *1' "$f" && pass=$((pass + 1))
done
case "$(basename "$JOB")" in
  full-*) total="/$(ls -d "${TB_TASKS:-$HOME/terminal-bench-2-1/tasks}"/*/ 2>/dev/null | wc -l)" ;;
  *) total="" ;;   # a subset: trials = tasks x N_TRIALS, which the job dir doesn't record
esac
running=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -c '__' || true)
alive=$(pgrep -f 'bin/harbor' >/dev/null && echo yes || echo NO)
log="jobs/$(basename "$JOB").log"            # subset runs log under the job's name
[ -f "$log" ] || log=jobs/full-run.log
age=$([ -f "$log" ] && echo "$(( $(date +%s) - $(stat -c %Y "$log") ))s" || echo "-")
echo "$(date +%H:%M) $JOB done=$done_n$total pass=$pass running=$running harbor=$alive log_age=$age"
