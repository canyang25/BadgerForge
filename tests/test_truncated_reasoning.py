"""What happens when the model spends its whole budget thinking.

Our baseline lost polyglot-c-py this way: 8k output tokens of unfinished
reasoning per turn, stored whole, resent every turn, the same truncated
thought emitted nine times, 1.07M tokens spent, task timed out.
"""

from agent.llm import REASONING_TAIL_CHARS, _tail


def test_short_response_is_left_alone():
    assert _tail("ls /app", REASONING_TAIL_CHARS) == "ls /app"


def test_long_response_is_cut_to_its_tail():
    thinking = "".join(f"step {i} " for i in range(5000))
    kept = _tail(thinking, REASONING_TAIL_CHARS)
    assert len(kept) < len(thinking) / 10
    assert kept.endswith(thinking[-200:])


def test_the_model_is_told_why_its_text_is_missing():
    kept = _tail("x" * 10_000, REASONING_TAIL_CHARS)
    assert "cut off" in kept
    assert "output budget" in kept


def test_a_full_turn_of_thinking_costs_about_one_percent_as_much():
    # 29,625 chars is what one turn actually cost us in the baseline.
    before = 29_625
    after = len(_tail("x" * before, REASONING_TAIL_CHARS))
    assert after < before * 0.1
