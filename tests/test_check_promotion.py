"""Exercise real local cherry-picks and pytest runs; no Docker or model."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

CHECKER = Path(__file__).resolve().parent.parent / "scripts/check_promotion.py"


@pytest.fixture
def history(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    git("config", "commit.gpgsign", "false")
    (repo / "tests").mkdir()
    (repo / "value.py").write_text("VALUE = 0\n")
    (repo / "tests/test_value.py").write_text(
        "from pathlib import Path\nimport value\n"
        "def test_candidate():\n"
        "    assert Path(value.__file__).resolve() == Path.cwd() / 'value.py'\n"
        "    assert value.VALUE == 0\n"
    )

    def commit(message):
        git("add", ".")
        git("commit", "-qm", message)
        return git("rev-parse", "HEAD")

    base = commit("base")

    def run(*commits, extra=(), environment=None):
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--repo", str(repo), "--base", base,
             *commits, *extra], capture_output=True, text=True, env=environment,
        )
        return result, json.loads(result.stdout)

    return repo, git, commit, base, run


def test_clean_pick_tests_candidate_and_leaves_source_unchanged(history):
    repo, git, commit, base, run = history
    (repo / "new.txt").write_text("new\n")
    change = commit("change")
    (repo / "uncommitted.txt").write_text("keep me\n")
    before = git("status", "--porcelain")
    result, report = run(change, environment={**os.environ, "PYTHONPATH": str(repo)})
    assert result.returncode == 0, report
    assert report["status"] == report["tests"] == "passed"
    assert report["base"] == base and report["applied"] == [change]
    assert git("rev-parse", "HEAD") == change
    assert git("status", "--porcelain") == before


def test_prerequisites_must_be_explicit_and_ordered(history):
    repo, _, commit, _, run = history
    (repo / "feature.txt").write_text("foundation\n")
    prerequisite = commit("foundation")
    (repo / "feature.txt").write_text("extension\n")
    extension = commit("extension")
    failed, report = run(extension)
    assert failed.returncode == 1
    assert report["status"] == "apply_failed" and report["tests"] == "not_run"
    assert report["conflicts"] == ["feature.txt"]
    passed, report = run(prerequisite, extension)
    assert passed.returncode == 0, report
    assert report["applied"] == [prerequisite, extension]


def test_failing_candidate_is_not_reported_as_promotable(history):
    repo, _, commit, _, run = history
    (repo / "value.py").write_text("VALUE = 1\n")
    result, report = run(commit("break value"))
    assert result.returncode == 1
    assert report["status"] == "tests_failed" and report["tests"] == "failed"
    assert "1 failed" in report["test_output"]


def test_apply_only_is_explicitly_unverified(history):
    repo, _, commit, _, run = history
    (repo / "value.py").write_text("VALUE = 1\n")
    result, report = run(commit("untested"), extra=["--apply-only"])
    assert result.returncode == 0
    assert report["status"] == "applied_without_tests" and report["tests"] == "not_run"


def test_unknown_revision_has_a_structured_failure(history):
    *_, run = history
    result, report = run("missing-ref")
    assert result.returncode == 1
    assert report["status"] == "error" and report["tests"] == "not_run"


def test_project_import_from_outside_candidate_fails_validation(history):
    repo, _, commit, _, run = history
    (repo / "tests/conftest.py").write_text(
        "import sys\nfrom types import ModuleType\n"
        "module = ModuleType('agent.leaked')\n"
        "module.__file__ = '/outside/candidate/agent/leaked.py'\n"
        "sys.modules['agent.leaked'] = module\n"
    )
    result, report = run(commit("simulate editable import leak"))
    assert result.returncode == 1
    assert report["status"] == "tests_failed"
    assert "Project imports outside candidate: agent.leaked" in report["test_output"]
