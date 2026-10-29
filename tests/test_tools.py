import pytest

from agent.tools import parse_action


@pytest.mark.parametrize("text, kind", [
    ("TASK_COMPLETE", "done"),
    (" \nTASK_COMPLETE\n ", "done"),
    ("All tests pass.\n\nTASK_COMPLETE", "done"),
    ("I am not ready to say TASK_COMPLETE yet.", "none"),
    ("The file must contain TASK_COMPLETE as its text.", "none"),
    ("TASK_COMPLETE_PENDING", "none"),
    ("```bash\necho TASK_COMPLETE\n```", "shell"),
])
def test_completion_requires_its_own_line(text, kind):
    assert parse_action(text).kind == kind
