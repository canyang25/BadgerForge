"""Shaping must keep the evidence needed to recover from failed commands."""

import pytest

from agent.graph.shape import classify_observation, shape_message
from agent.prompts import DUMP_NOTE, TRUNCATION_NOTE, observation_message

ROW = "1.5 2.5 3.5 4.5 5.5"


def shaped(observation, note=None):
    kind = classify_observation(observation)
    assert kind
    message = observation_message(observation)
    if note:
        message += f"\n\n{note}"
    return shape_message(message, observation, kind, note)


def test_numeric_summary_keeps_stderr_and_surrounding_stdout():
    observation = (
        "exit code: 1\nstdout:\nInput matrix:\n"
        + "\n".join([ROW] * 12)
        + "\nResidual exceeds tolerance.\nstderr:\n"
        "ValueError: input matrix is singular"
    )
    result = shaped(observation)
    assert "exit code: 1" in result
    assert "Input matrix:" in result
    assert "Residual exceeds tolerance." in result
    assert "stderr:\nValueError: input matrix is singular" in result
    assert "12 rows, about 5 columns" in result
    assert result.count(ROW) == 2


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_colored_errors_are_text(stream):
    lines = "\n".join(["\x1b[31mERROR: missing input file\x1b[0m"] * 8)
    observation = f"exit code: 1\n{stream}:\n{lines}"
    assert classify_observation(observation) == ""


def test_terminal_hyperlinks_are_text():
    link = "\x1b]8;;https://example.org/help\x1b\\Help\x1b]8;;\x1b\\"
    assert classify_observation("exit code: 1\nstderr:\n" + link * 16) == ""


@pytest.mark.parametrize("binary_stream", ["stdout", "stderr"])
def test_binary_lines_keep_readable_text_in_both_streams(binary_stream):
    streams = {
        "stdout": "input header\ncomputation failed",
        "stderr": "Traceback: invalid input\ncheck the file format",
    }
    streams[binary_stream] += "\n" + "\x00" * 40 + "\nend of diagnostic"
    observation = (
        f"exit code: 1\nstdout:\n{streams['stdout']}\nstderr:\n{streams['stderr']}"
    )
    result = shaped(observation)
    for text in (
        "input header", "computation failed", "Traceback: invalid input",
        "check the file format", "end of diagnostic",
    ):
        assert text in result
    assert "\x00" not in result
    assert "binary data" in result
    assert DUMP_NOTE in result


def test_separate_tables_keep_the_text_between_them():
    table = "\n".join([ROW] * 8)
    result = shaped(f"exit code: 0\nstdout:\n{table}\nSecond matrix:\n{table}\nDone.")
    assert result.count("numeric table") == 2
    assert result.count(ROW) == 4
    assert "Second matrix:" in result
    assert "Done." in result


def test_multiline_binary_dump_shrinks_instead_of_expanding_per_line():
    observation = "exit code: 1\nstdout:\n" + "\x00\n" * 1000
    result = shaped(observation)
    assert result.count("binary data:") == 1
    assert len(result) < len(observation)


def test_scattered_numeric_lines_are_not_a_table_dump():
    text = "\n".join([ROW + "\niteration complete"] * 8)
    assert classify_observation(f"exit code: 0\nstdout:\n{text}") == ""


def test_shaped_output_keeps_truncation_and_guard_notes_once():
    observation = (
        "exit code: 1\nstdout:\n" + "\n".join([ROW] * 8)
        + "\n... [100 characters omitted] ...\nstderr:\nfailed to converge"
    )
    note = "The previous command also failed; choose a different approach."
    result = shaped(observation, note)
    assert "failed to converge" in result
    assert result.count(note) == 1
    assert result.count(TRUNCATION_NOTE) == 1


def test_colored_numeric_table_keeps_colored_errors():
    rows = "\n".join([f"\x1b[32m{ROW}\x1b[0m"] * 8)
    observation = f"exit code: 1\nstdout:\n{rows}\nstderr:\n\x1b[31mERROR\x1b[0m"
    result = shaped(observation)
    assert "numeric table: 8 rows, about 5 columns" in result
    assert "stderr:\n\x1b[31mERROR\x1b[0m" in result
