"""scripts/run_full.sh resume: pin job_name in config.json before resuming.

harbor writes config.json with exclude_defaults, and job_name defaults to the
current second, so a job whose config is written in the second it was named
has no job_name on disk. `harbor jobs resume` then names a new job and reruns
every trial in a new directory instead of the unfinished ones. That happened
to batch 2's concise arm (a 39-trial rerun for one missing trial)."""

import json
import os
import subprocess
from pathlib import Path

RUN_FULL = Path(__file__).parent.parent / "scripts" / "run_full.sh"


def resume(tmp_path, job_arg):
    """Run `run_full.sh resume <job_arg>` with a fake harbor that records its args."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    harbor = bin_dir / "harbor"
    harbor.write_text('#!/usr/bin/env bash\necho "$@" > "$HARBOR_ARGS"\n')
    harbor.chmod(0o755)
    (tmp_path / "env").write_text("LLM_MODEL=m1\n")
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "ENV_FILE": str(tmp_path / "env"),
        "HARBOR_ARGS": str(tmp_path / "harbor-args"),
    }
    r = subprocess.run(
        ["bash", str(RUN_FULL), "resume", str(job_arg)], env=env, capture_output=True, text=True
    )
    recorded = tmp_path / "harbor-args"
    return r, recorded.read_text().split() if recorded.exists() else []


def make_job(tmp_path, config):
    inner = tmp_path / "jobs" / "full-20261015-1523" / "2026-10-15__15-23-55"
    inner.mkdir(parents=True)
    (inner / "config.json").write_text(json.dumps(config, indent=4))
    return inner


def test_adds_the_missing_job_name_before_resuming(tmp_path):
    inner = make_job(tmp_path, {"jobs_dir": "jobs/full-20261015-1523", "n_attempts": 3})
    r, args = resume(tmp_path, inner.parent)
    assert r.returncode == 0, r.stderr
    config = json.loads((inner / "config.json").read_text())
    assert config["job_name"] == "2026-10-15__15-23-55"
    assert config["n_attempts"] == 3
    assert args[:4] == ["jobs", "resume", "-p", str(inner)]


def test_works_when_given_the_inner_directory(tmp_path):
    inner = make_job(tmp_path, {"jobs_dir": "jobs/full-20261015-1523"})
    r, args = resume(tmp_path, inner)
    assert r.returncode == 0, r.stderr
    assert json.loads((inner / "config.json").read_text())["job_name"] == "2026-10-15__15-23-55"
    assert args[3] == str(inner)


def test_leaves_a_config_that_already_has_it_untouched(tmp_path):
    inner = make_job(
        tmp_path, {"job_name": "2026-10-15__15-23-55", "jobs_dir": "jobs/full-20261015-1523"}
    )
    before = (inner / "config.json").read_text()
    r, _ = resume(tmp_path, inner.parent)
    assert r.returncode == 0, r.stderr
    assert (inner / "config.json").read_text() == before
