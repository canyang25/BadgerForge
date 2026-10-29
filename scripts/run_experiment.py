"""Launch one controlled Harbor arm; use run_experiment.sh to load settings."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
DEV_TASKS = [
    "compile-compcert", "extract-elf", "feal-linear-cryptanalysis", "largest-eigenval",
    "modernize-scientific-stack", "portfolio-optimization", "regex-log",
    "reshard-c4-data", "sqlite-db-truncate", "write-compressor",
]
BASE_FLAGS = {
    "AGENT_MAX_TURNS": "100", "AGENT_COMMAND_TIMEOUT_SEC": "60",
    "AGENT_MAX_TURNS_WITHOUT_ACTION": "4", "AGENT_NO_COMMAND_TEMPERATURE": "0.7",
    "AGENT_PROGRESS_CHECK": "0", "AGENT_PROGRESS_EVERY": "10",
    "AGENT_OBSERVATION_SHAPE": "0",
}
PROFILES = {
    "control": {}, "progress": {"AGENT_PROGRESS_CHECK": "1"},
    "turns150": {"AGENT_MAX_TURNS": "150"},
    "shaping": {"AGENT_OBSERVATION_SHAPE": "1"},
}
MODEL_DEFAULTS = {
    "LLM_MODEL": "", "LLM_TEMPERATURE": "0.2", "LLM_MAX_TOKENS": "16384",
    "LLM_REASONING_EFFORT": "medium", "LLM_TIMEOUT_SEC": "300", "LLM_MAX_RETRIES": "5",
}


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("output", type=Path)
    parser.add_argument("tasks", nargs="*", help="defaults to the 10-task dev slice")
    parser.add_argument("--trials", type=positive, default=3)
    parser.add_argument("--concurrency", type=positive, default=2)
    parser.add_argument("--dry-run", action="store_true", help="preview without loading credentials or writing files")
    parser.add_argument("--allow-dirty", action="store_true", help="record a dirty checkout for a local smoke test")
    args = parser.parse_args(argv)
    try:
        return launch(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"experiment: {exc}\n")


def launch(args):
    candidates = [Path.home() / "Documents/terminal-bench-2-1/tasks", Path.home() / "terminal-bench-2-1/tasks"]
    dataset = Path(os.environ["TB_TASKS"]) if "TB_TASKS" in os.environ else next(
        (path for path in candidates if path.is_dir()), candidates[0]
    )
    dataset = dataset.resolve()
    tasks = args.tasks or DEV_TASKS
    if len(tasks) != len(set(tasks)):
        raise ValueError("task names must be unique")
    for task in tasks:
        if Path(task).name != task or task in (".", "..") or not (dataset / task).is_dir():
            raise ValueError(f"no such task under {dataset}: {task}")
    job = args.output.resolve()
    if job.exists():
        raise ValueError(f"output already exists: {job}; choose a fresh directory")
    if (ROOT / ".env").exists():
        raise ValueError("plain .env would override the recorded settings; use .env.op.local")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    if dirty and not args.dry_run and not args.allow_dirty:
        raise ValueError("checkout is dirty; commit changes or use --allow-dirty for a smoke test")
    environment = {**os.environ, **BASE_FLAGS, **PROFILES[args.profile]}
    settings = {**{key: environment.get(key, default) for key, default in MODEL_DEFAULTS.items()},
                **{key: environment[key] for key in BASE_FLAGS}}
    command = ["harbor", "run", "-p", str(dataset)]
    for task in tasks:
        command.extend(["-i", task])
    command.extend(["--agent", "agent.agent:BaselineAgent", "-k", str(args.trials),
                    "-n", str(args.concurrency), "-o", str(job)])
    manifest = {"profile": args.profile, "commit": commit, "dirty": dirty,
                "tasks": tasks, "settings": settings, "command": command,
                "trials": args.trials, "concurrency": args.concurrency, "status": "planned"}
    if args.dry_run:
        print(json.dumps(manifest, indent=2))
        return 0
    if not environment.get("LLM_MODEL"):
        raise ValueError("LLM_MODEL is required; run through scripts/run_experiment.sh")
    if not shutil.which("harbor", path=environment.get("PATH")):
        raise ValueError("harbor is not installed in the active environment")
    job.mkdir(parents=True, exist_ok=False)
    manifest.update(status="running", started_at=datetime.now(timezone.utc).isoformat())
    path = job / "experiment.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Experiment {args.profile}: {len(tasks)} tasks x {args.trials}; manifest: {path}", flush=True)
    try:
        code = subprocess.run(command, cwd=ROOT, env=environment).returncode
    except KeyboardInterrupt:
        code = 130
    except OSError as exc:
        print(f"experiment: could not start Harbor: {exc}", file=sys.stderr)
        code = 127
    manifest.update(status="completed" if code == 0 else "failed", return_code=code,
                    finished_at=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    raise SystemExit(main())
