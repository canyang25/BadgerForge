"""Graph state for one task.

The model client, the container, and Harbor's context object stay off this
schema. They are not useful in a checkpoint, and the loop reads them from
``GraphContext`` instead. Counters here are the ones the old loop kept in
local variables, so a run reports the same metadata.
"""

from pydantic import BaseModel, Field

from agent.loop_guard import LoopGuard


class AgentState(BaseModel):
    """What one node hands the next node."""

    messages: list[dict] = Field(default_factory=list)
    guard: LoopGuard = Field(default_factory=LoopGuard)
    turns: int = 0
    n_input: int = 0
    n_output: int = 0
    finished: bool = False
    turns_without_action: int = 0
    stop_reason: str | None = None
    stopped_by_guard: str | None = None
    no_command_replies: int = 0
    commands_after_bump: int = 0
    next_temperature: float | None = None
    last_truncated: bool = False
    action_kind: str = ""
    command: str = ""
    before_note: str | None = None
    run_command: bool = False
    node_trace: list[dict] = Field(default_factory=list)
