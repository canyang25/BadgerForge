import asyncio
import os
from pathlib import Path
import subprocess

import pytest
from harbor.cli import jobs
from harbor.models.job.config import JobConfig
from harbor.models.task.id import LocalTaskId
from harbor.models.trial.config import TaskConfig, TrialConfig
from harbor.models.trial.result import AgentInfo, ExceptionInfo, TrialResult
from harbor.trial.errors import EnvironmentStartTimeoutError

RUN_FULL = Path(__file__).parent.parent / "scripts" / "run_full.sh"


@pytest.mark.parametrize("interruption", [asyncio.CancelledError(), EnvironmentStartTimeoutError()])
def test_resume_retries_interrupted_trials_and_keeps_finished_trials(
    tmp_path, monkeypatch, interruption
):
    job = tmp_path / "job with spaces"
    job.mkdir()
    (job / "config.json").write_text(JobConfig().model_dump_json())
    for name, error in [("interrupted", interruption), ("finished", None)]:
        trial = job / name
        trial.mkdir()
        result = TrialResult(
            task_name="test", trial_name=name, trial_uri=trial.as_uri(),
            task_id=LocalTaskId(path=tmp_path), task_checksum="test",
            config=TrialConfig(task=TaskConfig(path=tmp_path)),
            agent_info=AgentInfo(name="test", version="test"),
            exception_info=ExceptionInfo.from_exception(error) if error else None,
        )
        (trial / "result.json").write_text(result.model_dump_json())

    env_file = tmp_path / "env"
    env_file.write_text("LLM_MODEL=test\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    harbor = bin_dir / "harbor"
    harbor.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@"\n')
    harbor.chmod(0o755)
    process = subprocess.run(
        ["bash", str(RUN_FULL), "resume", str(job)],
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
             "ENV_FILE": str(env_file)},
        capture_output=True, text=True,
    )
    assert process.returncode == 0, process.stderr
    args = process.stdout.splitlines()[1:]
    assert args[:4] == ["jobs", "resume", "-p", str(job)]
    filters = [args[i + 1] for i, arg in enumerate(args[:-1]) if arg == "-f"]

    def stop_before_execution(config):
        raise RuntimeError("stop before execution")

    monkeypatch.setattr(jobs, "_run_preflight", stop_before_execution)
    with pytest.raises(RuntimeError, match="stop before execution"):
        jobs.resume(job, filter_error_types=filters)
    assert not (job / "interrupted").exists()
    assert (job / "finished" / "result.json").exists()
