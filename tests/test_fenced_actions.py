import subprocess

import pytest

from agent.tools import parse_action


@pytest.mark.parametrize("language", ["bash", "sh", "shell", ""])
def test_supported_shell_fences(language):
    action = parse_action(f"```{language}\necho ready\n```")
    assert action.kind == "shell"
    assert action.command == "echo ready"


def test_markdown_heredoc_is_written_in_full(tmp_path):
    document = "# Demo\n\n```python\nprint('hello')\n```\n"
    command = f"cat > README.md <<'EOF'\n{document}EOF"
    action = parse_action(f"````bash\n{command}\n````")
    assert action.kind == "shell"
    result = subprocess.run(
        ["bash", "-c", action.command], cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "README.md").read_text() == document


def test_inline_backticks_do_not_end_a_command():
    command = "printf '%s\\n' '```'"
    assert parse_action(f"```bash\n{command}\n```").command == command


def test_non_shell_blocks_are_skipped_without_executing_prose():
    text = "```python\nprint('example')\n```\nNow run this:\n```bash\necho ready\n```"
    assert parse_action(text).command == "echo ready"


def test_unsupported_language_is_not_executed():
    assert parse_action("```python\nprint('example')\n```").kind == "none"


def test_a_shorter_closing_fence_does_not_complete_an_action():
    assert parse_action("````bash\necho ready\n```").kind == "none"


def test_a_longer_closing_fence_is_allowed():
    assert parse_action("````bash\necho ready\n`````").command == "echo ready"


def test_indented_fences_are_supported():
    assert parse_action("  ```bash\necho ready\n  ```").command == "echo ready"
