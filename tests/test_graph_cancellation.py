"""Harbor must retain useful partial results when a task is cancelled."""

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from harbor.models.agent.context import AgentContext

from agent.graph import run_graph
from agent.graph.context import GraphContext
from agent.state import AgentState


class PausingLLM:
    last_truncated = False

    def __init__(self, pause_at, entered):
        self.pause_at = pause_at
        self.entered = entered
        self.calls = 0
        self.cancelled = False

    async def chat(self, messages, temperature=None):
        self.calls += 1
        if self.calls == self.pause_at:
            self.entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return (
            f"```bash\necho {self.calls}\n```",
            {"prompt_tokens": 10, "completion_tokens": 5},
        )


class PausingEnvironment:
    def __init__(self, pause_at, entered):
        self.pause_at = pause_at
        self.entered = entered
        self.commands = []
        self.cancelled = False

    async def exec(self, command, timeout_sec):
        self.commands.append(command)
        if len(self.commands) == self.pause_at:
            self.entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return SimpleNamespace(
            stdout=f"completed {len(self.commands)}", stderr="", return_code=0
        )


@pytest.mark.parametrize(
    "stage, pause_at, turns, expected_nodes, message_count",
    [
        ("model", 1, 0, [], 2),
        ("model", 2, 1, ["call_model", "guard", "execute"], 4),
        ("command", 1, 1, ["call_model", "guard"], 3),
        (
            "command", 2, 2,
            ["call_model", "guard", "execute", "call_model", "guard"], 5,
        ),
    ],
)
def test_cancellation_preserves_completed_work(
    stage, pause_at, turns, expected_nodes, message_count
):
    async def scenario():
        entered = asyncio.Event()
        llm = PausingLLM(pause_at if stage == "model" else None, entered)
        environment = PausingEnvironment(
            pause_at if stage == "command" else None, entered
        )
        harbor = AgentContext(metadata={"run_label": "retained"})
        initial_messages = [
            {"role": "system", "content": "Use one command per turn."},
            {"role": "user", "content": "Write the deliverable."},
        ]
        context = GraphContext(
            llm=llm,
            environment=environment,
            logger=logging.getLogger(__name__),
            harbor=harbor,
            max_turns=10,
            max_turns_without_action=4,
            command_timeout_sec=60,
            no_command_temperature=0.7,
        )
        task = asyncio.create_task(
            run_graph(AgentState(messages=initial_messages), context)
        )
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        assert (llm if stage == "model" else environment).cancelled
        assert harbor.n_input_tokens == turns * 10
        assert harbor.n_output_tokens == turns * 5
        meta = harbor.metadata
        assert meta["turns"] == turns
        assert meta["finished"] is False
        assert meta["run_label"] == "retained"
        assert [row["node"] for row in meta["node_trace"]] == expected_nodes
        assert len(meta["messages"]) == message_count
        assert meta["messages"][:2] == initial_messages
        assert sum(row["prompt_tokens"] for row in meta["node_trace"]) == turns * 10
        assert len(environment.commands) == (pause_at - 1 if stage == "model" else pause_at)
        if stage == "command":
            assert meta["messages"][-1]["role"] == "assistant"
        json.dumps(meta)

    asyncio.run(scenario())
