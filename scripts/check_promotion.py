"""Apply selected commits and test them in a disposable local clone.

Uses the active Python environment; does not install dependencies, fetch remote
refs, load credentials, update the source checkout, or establish score parity.
Only run trusted repository tests. Output is a JSON report, including failures.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PYTEST_GUARD = """
from pathlib import Path
import sys
import pytest
root = Path.cwd().resolve()
code = int(pytest.main(sys.argv[1:]))
outside = []
for name, module in list(sys.modules.items()):
    source = getattr(module, '__file__', None)
    if name.split('.')[0] in {'agent', 'eval'} and source:
        if not Path(source).resolve().is_relative_to(root):
            outside.append(name)
if outside:
    print('Project imports outside candidate: ' + ', '.join(sorted(outside)))
    code = 1
raise SystemExit(code)
"""


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def revision(repo, ref):
    result = git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
    if result.returncode:
        raise ValueError(f"not a local commit: {ref}")
    return result.stdout.strip()


def check(repo, base, commits, targets, apply_only=False):
    report = {"status": "error", "base": revision(repo, base),
              "commits": [revision(repo, ref) for ref in commits], "applied": [],
              "tests": "not_run", "python": sys.executable}
    with tempfile.TemporaryDirectory(prefix="badgerforge-promotion-") as directory:
        checkout = Path(directory) / "checkout"
        result = subprocess.run(
            ["git", "clone", "--local", "--no-hardlinks", "--no-checkout", "--",
             str(repo), str(checkout)], capture_output=True, text=True,
        )
        if result.returncode:
            report["error"] = result.stderr
            return report, 1
        result = git(checkout, "checkout", "--detach", report["base"])
        if result.returncode:
            report["error"] = result.stderr
            return report, 1
        for commit in report["commits"]:
            result = git(checkout, "cherry-pick", "--no-commit", commit)
            if result.returncode:
                report.update(status="apply_failed", failed_commit=commit,
                              conflicts=git(checkout, "diff", "--name-only",
                                            "--diff-filter=U").stdout.splitlines(),
                              error=result.stdout + result.stderr)
                return report, 1
            report["applied"].append(commit)
        if apply_only:
            report["status"] = "applied_without_tests"
            return report, 0
        # Resolve project imports from this candidate, even when the active
        # interpreter has an editable install pointing at the source checkout.
        environment = {**os.environ, "PYTHONPATH": str(checkout)}
        environment.pop("LLM_API_KEY", None)
        # An editable-install finder can supply a missing submodule from the
        # original checkout. Reject that leak even if the assertions passed.
        command = [sys.executable, "-c", PYTEST_GUARD, "-q", *targets]
        result = subprocess.run(command, cwd=checkout, env=environment,
                                capture_output=True, text=True)
        report.update(status="passed" if result.returncode == 0 else "tests_failed",
                      tests="passed" if result.returncode == 0 else "failed",
                      command=command, test_return_code=result.returncode,
                      test_output=result.stdout + result.stderr)
        return report, 0 if result.returncode == 0 else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commits", nargs="+", help="prerequisites first, then the change")
    parser.add_argument("--base", required=True, help="local target branch or commit")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--test", action="append", help="pytest target; default: full tests/")
    parser.add_argument("--apply-only", action="store_true", help="check application without tests")
    args = parser.parse_args(argv)
    try:
        report, code = check(args.repo.resolve(), args.base, args.commits,
                             args.test or ["tests"], args.apply_only)
    except (OSError, ValueError) as exc:
        report, code = {"status": "error", "tests": "not_run", "error": str(exc)}, 1
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
