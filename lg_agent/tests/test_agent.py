import pytest
from unittest.mock import MagicMock
from lg_agent.graph import create_agent_graph

@pytest.mark.asyncio
async def test_agent_graph_instantiation():
    env = MagicMock()
    graph = create_agent_graph(env)
    assert graph is not None

    # Just testing we can compile it without errors.
    # To run a full test against the LLM, we'd need an active connection.
    # But this test guarantees the graph builds.
