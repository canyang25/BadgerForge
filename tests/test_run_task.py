import os
from pathlib import Path
import subprocess

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"


@pytest.mark.parametrize("layout, override", [
    ("Documents/terminal-bench-2-1/tasks", None),
    ("terminal-bench-2-1/tasks", None),
    ("custom tasks", "custom tasks"),
    ("terminal-bench-2-1/tasks", "missing"),
])
def test_single_task_finds_documented_paths_and_respects_overrides(tmp_path, layout, override):
    home_dir = tmp_path / "home with spaces"
    (home_dir / layout / "regex-log").mkdir(parents=True)
    scripts = tmp_path / "repo" / "scripts"
    scripts.mkdir(parents=True)
    launcher = scripts / "run_task.sh"
    launcher.write_text((SCRIPTS / "run_task.sh").read_text().replace("$HOME", "$BF_TEST_HOME"))
    (scripts / "env.sh").write_text((SCRIPTS / "env.sh").read_text())
    env_file = tmp_path / "env"
    env_file.write_text("LLM_MODEL=test\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    harbor = bin_dir / "harbor"
    harbor.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@"\n')
    harbor.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "ENV_FILE": str(env_file), "BF_TEST_HOME": str(home_dir)}
    env.pop("TB_TASKS", None)
    if override is not None:
        env["TB_TASKS"] = str(home_dir / override)
    result = subprocess.run(
        ["bash", str(launcher), "regex-log"], env=env, capture_output=True, text=True,
    )
    if override == "missing":
        assert result.returncode != 0
        assert str(home_dir / "missing" / "regex-log") in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            "run", "-p", str(home_dir / layout / "regex-log"),
            "--agent", "agent.agent:BaselineAgent",
        ]
