"""Run-scoped dependencies for one graph invocation.

LangGraph copies state between nodes. The client, the container, and Harbor's
context are passed beside the state so nodes can reach them without stuffing
live objects into the checkpoint.
"""

import logging
from dataclasses import dataclass
from typing import Any

from harbor.models.agent.context import AgentContext


@dataclass
class GraphContext:
    """Everything a node needs that is not part of ``AgentState``."""

    llm: Any
    environment: Any
    logger: logging.Logger
    harbor: AgentContext
    max_turns: int
    max_turns_without_action: int
    command_timeout_sec: int
    no_command_temperature: float
