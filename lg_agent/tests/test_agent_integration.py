import pytest
import os
import asyncio
from unittest.mock import MagicMock
from lg_agent.graph import create_agent_graph
from harbor.environments.base import ExecResult

@pytest.mark.asyncio
async def test_agent_graph_instantiation():
    env = MagicMock()
    graph = create_agent_graph(env)
    assert graph is not None

@pytest.mark.asyncio
async def test_agent_llm_interaction():
    # Only run if we specifically want to test the LLM integration
    # Since we have the API key = "dummy" and base_url pointing to the internal gateway, it should work.
    env = MagicMock()
    env.exec.return_value = ExecResult(stdout="dummy output", stderr="", return_code=0)
    
    graph = create_agent_graph(env)
    
    from langchain_core.messages import SystemMessage, HumanMessage
    
    initial_state = {
        "messages": [
            SystemMessage(content="You have a tool ExecuteCommand to run bash commands and FinishTask to finish. "
                                  "Please run the command 'echo hello' and then finish the task."),
            HumanMessage(content="Please start.")
        ],
        "finished": False,
        "input_tokens": 0,
        "output_tokens": 0
    }
    
    # We will just run 2 iterations manually to see if it calls the tool
    state = initial_state
    
    # First step (LLM call)
    state = await graph.ainvoke(state)
    
    assert "messages" in state
    assert len(state["messages"]) > 2
    # Verify it finished or used tools
    # It should have called ExecuteCommand and maybe FinishTask
