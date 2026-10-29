"""Exercise the launcher with a fake Harbor; no Docker or model calls."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

LAUNCHER = Path(__file__).parent.parent / "scripts/run_experiment.sh"
REAL_GIT = shutil.which("git")


@pytest.fixture
def runner(tmp_path):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    git = binaries / "git"
    git.write_text(
        '#!/bin/sh\n'
        'if [ "$PWD" = "$TB_TASKS" ]; then exec "$TEST_REAL_GIT" "$@"; fi\n'
        'if [ "$1" = rev-parse ]; then echo commit123; else printf "%s" "${TEST_DIRTY:-}"; fi\n'
    )
    git.chmod(0o755)
    harbor = binaries / "harbor"
    harbor.write_text(
        '#!/usr/bin/env python3\nimport json, os, sys\n'
        'from pathlib import Path\n'
        'Path(os.environ["HARBOR_RECORD"]).write_text(json.dumps({"args": sys.argv[1:], '
        '"flags": {k: v for k, v in os.environ.items() if k.startswith("AGENT_")}}))\n'
        'sys.exit(int(os.environ.get("HARBOR_EXIT", "0")))\n'
    )
    harbor.chmod(0o755)
    dataset = tmp_path / "task data"
    (dataset / "regex-log").mkdir(parents=True)
    env_file = tmp_path / "gateway"
    env_file.write_text(
        "LLM_MODEL=test-model\nLLM_API_KEY=private-test-sentinel\n"
        "AGENT_PROGRESS_CHECK=1\nAGENT_OBSERVATION_SHAPE=1\nAGENT_MAX_TURNS=999\n"
        "AGENT_EARLY_DELIVERABLE=1\nAGENT_DELIVERABLE_TURN=42\n"
    )
    environment = {**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}",
                   "ENV_FILE": str(env_file), "TB_TASKS": str(dataset.resolve()),
                   "TEST_REAL_GIT": REAL_GIT,
                   "BF_PYTHON": sys.executable, "HARBOR_RECORD": str(tmp_path / "record")}

    def run(profile="control", extra=(), **overrides):
        return subprocess.run(
            ["bash", str(LAUNCHER), profile, str(tmp_path / "job"), "regex-log", *extra],
            env={**environment, **overrides}, capture_output=True, text=True,
        )
    return run


@pytest.mark.parametrize("profile, turns, progress, shaping, deliverable", [
    ("control", "100", "0", "0", "0"), ("progress", "100", "1", "0", "0"),
    ("turns150", "150", "0", "0", "0"), ("shaping", "100", "0", "1", "0"),
    ("deliverable", "100", "0", "0", "1"),
])
def test_profiles_override_gateway_file_and_record_only_selected_settings(
    runner, tmp_path, profile, turns, progress, shaping, deliverable
):
    result = runner(profile)
    assert result.returncode == 0, result.stderr
    manifest_text = (tmp_path / "job/experiment.json").read_text()
    manifest = json.loads(manifest_text)
    actual = json.loads((tmp_path / "record").read_text())
    for key, expected in (("AGENT_MAX_TURNS", turns), ("AGENT_PROGRESS_CHECK", progress),
                          ("AGENT_OBSERVATION_SHAPE", shaping),
                          ("AGENT_EARLY_DELIVERABLE", deliverable), ("AGENT_DELIVERABLE_TURN", "5")):
        assert actual["flags"][key] == manifest["settings"][key] == expected
    assert manifest["commit"] == "commit123"
    assert manifest["settings"]["LLM_MODEL"] == "test-model"
    assert manifest["status"] == "completed"
    assert actual["args"][actual["args"].index("-k") + 1] == "3"
    assert "private-test-sentinel" not in manifest_text + result.stdout + result.stderr
    assert "LLM_API_KEY" not in manifest["settings"]


def test_dry_run_needs_no_gateway_file_and_writes_nothing(runner, tmp_path):
    result = runner(extra=["--dry-run"], ENV_FILE=str(tmp_path / "missing"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "planned"
    assert not (tmp_path / "job").exists()
    assert not (tmp_path / "record").exists()


def test_existing_output_is_never_reused(runner, tmp_path):
    (tmp_path / "job").mkdir()
    result = runner()
    assert result.returncode != 0
    assert "output already exists" in result.stderr
    assert not (tmp_path / "record").exists()


def test_dirty_checkout_requires_an_explicit_smoke_test(runner, tmp_path):
    result = runner(TEST_DIRTY=" M agent/agent.py")
    assert result.returncode != 0
    assert not (tmp_path / "job").exists()
    result = runner(extra=["--allow-dirty"], TEST_DIRTY=" M agent/agent.py")
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "job/experiment.json").read_text())["dirty"] is True


def test_harbor_failure_is_preserved_in_exit_status_and_manifest(runner, tmp_path):
    result = runner(HARBOR_EXIT="7")
    assert result.returncode == 7
    manifest = json.loads((tmp_path / "job/experiment.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["return_code"] == 7


def test_harbor_start_failure_is_recorded(runner, tmp_path):
    (tmp_path / "bin/harbor").write_text("#!/missing/interpreter\n")
    result = runner()
    assert result.returncode == 127
    assert json.loads((tmp_path / "job/experiment.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("task", ["../outside", "regex-log"])
def test_invalid_or_duplicate_task_names_do_not_start_harbor(runner, tmp_path, task):
    assert runner(extra=[task]).returncode != 0
    assert not (tmp_path / "record").exists()


@pytest.mark.parametrize("arguments", [["--trials", "0"], ["--concurrency", "-1"]])
def test_invalid_counts_do_not_start_harbor(runner, tmp_path, arguments):
    assert runner(extra=arguments).returncode != 0
    assert not (tmp_path / "record").exists()


def version_dataset(tmp_path):
    dataset = tmp_path / "task data"
    (dataset / "regex-log/input.txt").write_text("original\n")
    for args in [("init", "-q"), ("config", "user.name", "Test"),
                 ("config", "user.email", "test@example.invalid"),
                 ("config", "commit.gpgsign", "false"), ("add", "."),
                 ("commit", "-qm", "dataset")]:
        subprocess.run([REAL_GIT, *args], cwd=dataset, check=True, capture_output=True)
    return subprocess.check_output([REAL_GIT, "rev-parse", "HEAD"], cwd=dataset, text=True).strip()


def test_manifest_records_the_actual_dataset_revision(runner, tmp_path):
    revision = version_dataset(tmp_path)
    result = runner()
    assert result.returncode == 0, result.stderr
    info = json.loads((tmp_path / "job/experiment.json").read_text())["dataset"]
    assert info == {"path": str((tmp_path / "task data").resolve()),
                    "commit": revision, "selected_tasks_dirty": False}


@pytest.mark.parametrize("changed", ["input.txt", "untracked.txt"])
def test_changed_selected_tasks_require_an_explicit_smoke_test(runner, tmp_path, changed):
    version_dataset(tmp_path)
    (tmp_path / "task data/regex-log" / changed).write_text("changed\n")
    result = runner()
    assert result.returncode != 0 and "selected task files are dirty" in result.stderr
    assert not (tmp_path / "record").exists()
    assert not (tmp_path / "job").exists()
    result = runner(extra=["--allow-dirty"])
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "job/experiment.json").read_text())["dataset"]["selected_tasks_dirty"] is True


def test_changes_outside_the_selected_tasks_do_not_block_a_run(runner, tmp_path):
    version_dataset(tmp_path)
    (tmp_path / "task data/.DS_Store").write_text("unrelated\n")
    result = runner()
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "job/experiment.json").read_text())["dataset"]["selected_tasks_dirty"] is False


def test_unversioned_dataset_is_recorded_as_unknown(runner, tmp_path):
    result = runner()
    assert result.returncode == 0, result.stderr
    info = json.loads((tmp_path / "job/experiment.json").read_text())["dataset"]
    assert info["commit"] is None and info["selected_tasks_dirty"] is None
