import os
from pathlib import Path
import subprocess

import pytest

RUN_FULL = Path(__file__).parent.parent / "scripts" / "run_full.sh"


@pytest.mark.parametrize("nested", [False, True])
def test_resume_includes_rate_limit_failures(tmp_path, nested):
    job = tmp_path / "job with spaces"
    config_dir = job / "harbor-id" if nested else job
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text("{}")
    env_file = tmp_path / "env"
    env_file.write_text("LLM_MODEL=test\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    harbor = bin_dir / "harbor"
    harbor.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@"\n')
    harbor.chmod(0o755)
    result = subprocess.run(
        ["bash", str(RUN_FULL), "resume", str(job)],
        env={"PATH": f"{bin_dir}:{os.environ['PATH']}",
             "ENV_FILE": str(env_file), "TB_TASKS": str(tmp_path / "tasks")},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[1:] == [
        "jobs", "resume", "-p", str(config_dir),
        "-f", "APIConnectionError", "-f", "APITimeoutError",
        "-f", "InternalServerError", "-f", "RateLimitError",
        "-f", "AuthenticationError",
    ]
