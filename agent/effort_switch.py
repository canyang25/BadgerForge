"""Drop to a lower reasoning effort when a task is running long.

At the server's default effort the agent got half as many wrong answers as at
medium on the 2026-11-19 full run, but twice as many timeouts: 8 tasks that
pass at medium ran out of time. Time goes into thinking, about 5-6 s per 1,000
output tokens, and the trials that timed out averaged 4-5k output tokens per
turn against under 1k for passes (docs/experiments.md, 11-19).

So start at the default effort and, once the task has run a while and the
recent replies are long, switch to a lower effort for the rest of the task.
Short tasks and quick turns never switch.

The agent doesn't know its task's time limit (Harbor enforces it but doesn't
pass it in), so this uses time since ``run()`` started. That is the same WSL
clock Harbor's limit follows, so clock drift affects both alike.
"""

import time
from collections import deque
from typing import Callable


class EffortSwitch:
    """Decides, once per task, when to lower the reasoning effort.

    Parameters
    ----------
    target : str
        The effort to switch to (e.g. ``"medium"``). Empty means off.
    after_sec : float
        Never switch before this much time has passed since ``run()`` began.
    min_tokens : float
        Switch only if the last ``window`` replies averaged at least this many
        completion tokens.
    window : int
        How many recent replies to average.
    clock : callable
        Monotonic clock in seconds; injectable for tests.
    """

    def __init__(
        self,
        target: str,
        after_sec: float,
        min_tokens: float,
        window: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.target = target
        self.after_sec = after_sec
        self.min_tokens = min_tokens
        self.clock = clock
        self.start = clock()
        self.recent: deque[int] = deque(maxlen=window)
        self.switched_turn: int | None = None
        self.switched_elapsed: float | None = None

    def elapsed(self) -> float:
        return self.clock() - self.start

    def record(self, completion_tokens: int, turn: int) -> bool:
        """Record one reply's completion tokens; return True if we switch now."""
        self.recent.append(completion_tokens)
        if not self.target or self.switched_turn is not None:
            return False
        if self.elapsed() < self.after_sec:
            return False
        if len(self.recent) < self.recent.maxlen:
            return False
        if sum(self.recent) / len(self.recent) < self.min_tokens:
            return False
        self.switched_turn = turn
        self.switched_elapsed = round(self.elapsed(), 1)
        return True
