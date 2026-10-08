"""scripts/env.sh: op:// references are resolved with the 1Password CLI, or
kept from the environment when already set (the Windows launcher passes the
key in through WSLENV); a failed read is an error, never an empty key.

The first full run on Windows hit the empty-key case: op.exe failed inside
WSL, env.sh exported LLM_API_KEY="" without complaint, and the gateway
answered 401 to every request."""

import os
import subprocess
from pathlib import Path

ENV_SH = Path(__file__).parent.parent / "scripts" / "env.sh"


def source(tmp_path, env_file, fake_op, extra_env=None):
    """Source env.sh with a fake `op` on PATH; return the completed process."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    op = bin_dir / "op"
    op.write_text("#!/usr/bin/env bash\n" + fake_op + "\n")
    op.chmod(0o755)
    (tmp_path / "env").write_text(env_file)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "ENV_FILE": str(tmp_path / "env"),
    }
    env.update(extra_env or {})
    script = f'source "{ENV_SH}" && echo "KEY=${{LLM_API_KEY:-}} MODEL=${{LLM_MODEL:-}}"'
    return subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
    )


def test_resolves_the_reference_and_exports_plain_values(tmp_path):
    r = source(tmp_path, "LLM_MODEL=m1\nLLM_API_KEY=op://v/i/credential\n", 'echo "sk-test"')
    assert r.returncode == 0, r.stderr
    assert "KEY=sk-test MODEL=m1" in r.stdout


def test_a_failed_read_is_an_error_not_an_empty_key(tmp_path):
    r = source(tmp_path, "LLM_API_KEY=op://v/i/credential\n", 'echo "no session" >&2; exit 1')
    assert r.returncode != 0
    assert "KEY=" not in r.stdout
    assert "could not read LLM_API_KEY" in r.stderr


def test_an_empty_read_is_an_error_too(tmp_path):
    r = source(tmp_path, "LLM_API_KEY=op://v/i/credential\n", "echo")
    assert r.returncode != 0
    assert "KEY=" not in r.stdout


def test_a_value_already_in_the_environment_is_kept_and_op_is_not_called(tmp_path):
    r = source(
        tmp_path,
        "LLM_MODEL=m1\nLLM_API_KEY=op://v/i/credential\n",
        'touch "$PWD/op-was-called"; exit 1',
        {"LLM_API_KEY": "sk-from-windows"},
    )
    assert r.returncode == 0, r.stderr
    assert "KEY=sk-from-windows MODEL=m1" in r.stdout
    assert not (tmp_path / "op-was-called").exists()


def test_strips_the_carriage_return_op_exe_appends(tmp_path):
    r = source(tmp_path, "LLM_API_KEY=op://v/i/credential\n", "printf 'sk-win\\r\\n'")
    assert r.returncode == 0, r.stderr
    assert "KEY=sk-win MODEL=" in r.stdout
