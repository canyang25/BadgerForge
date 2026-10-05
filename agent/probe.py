"""Survey the container before the model's first turn.

Asking the model to look around first didn't work: with "survey the
environment" in the system prompt, behaviour barely changed (see
docs/experiments.md, 2026-10-05). So the agent code does the survey itself and
hands the result to the model with the task instruction.

Nothing here is task-specific. It reports what any task might need to know:
unusual top-level directories, what is in the working directory, which
package managers exist, and whether the network is reachable.
"""

from __future__ import annotations

import os

from harbor.environments.base import BaseEnvironment

PROBE_ENABLED = os.environ.get("AGENT_ENV_PROBE", "1") != "0"
PROBE_TIMEOUT_SEC = 20

PROBE_MAX_CHARS = 1500
"""The survey goes in the first message and is resent every turn, so it has
to stay small: at ~25 turns a task, every 100 characters here costs ~600
input tokens per task."""

# Standard FHS directories; anything else at the top level is worth mentioning.
_STANDARD_DIRS = (
    "bin boot dev etc home lib lib32 lib64 libx32 media mnt opt proc root run "
    "sbin srv sys tmp usr var"
)

PROBE_COMMAND = f"""
echo "working dir: $(pwd)"
ls -la | head -n 25
echo
echo "non-standard top-level dirs:"
for d in /*; do
  n=$(basename "$d")
  case " {_STANDARD_DIRS} " in *" $n "*) ;; *)
    [ -d "$d" ] && echo "  $d: $(ls -A "$d" 2>/dev/null | head -n 8 | tr '\\n' ' ')" ;;
  esac
done
[ -n "$(ls -A /opt 2>/dev/null)" ] && echo "  /opt: $(ls -A /opt | head -n 8 | tr '\\n' ' ')"
echo
echo "package managers: $(for p in apt-get pip3 pip uv conda npm cargo go; do command -v $p >/dev/null 2>&1 && printf '%s ' $p; done)"
if timeout 5 bash -c 'exec 3<>/dev/tcp/pypi.org/443' 2>/dev/null; then
  echo "network: reachable"
else
  echo "network: unreachable"
fi
"""


def format_survey(raw: str) -> str:
    """Trim the survey and frame it for the model."""
    text = raw.strip()
    if len(text) > PROBE_MAX_CHARS:
        text = text[:PROBE_MAX_CHARS] + "\n... [survey truncated]"
    return (
        "Environment survey, collected automatically before your first turn:\n"
        f"```\n{text}\n```"
    )


async def survey(environment: BaseEnvironment) -> str | None:
    """Run the probe. Returns None on any failure — the task goes ahead
    without it rather than failing because of it."""
    if not PROBE_ENABLED:
        return None
    try:
        result = await environment.exec(
            command=PROBE_COMMAND, timeout_sec=PROBE_TIMEOUT_SEC
        )
    except Exception:
        return None
    if not result.stdout:
        return None
    return format_survey(result.stdout)
