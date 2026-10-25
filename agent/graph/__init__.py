"""The baseline loop as a LangGraph.

::

    START -> call_model
               done  -> END
               none  -> nudge -> call_model | END
               shell -> guard
                          refuse -> call_model | END
                          run    -> execute -> call_model | END

``call_model``, ``nudge``, ``guard``, and ``execute`` each live in their own
file. A new experiment is another node plus an edge in ``build_graph``.
Tracing is the ``node=`` log line and ``context.metadata["node_trace"]``.
LangSmith stays off until plan.md's open question is settled.

Run the decisions without Harbor or a model::

    pytest tests/test_graph.py tests/test_no_command_reply.py -q

A real task is unchanged: ``./scripts/run_task.sh regex-log``.
"""

from langgraph.graph import END, START, StateGraph

from agent.graph.call_model import call_model
from agent.graph.context import GraphContext
from agent.graph.execute import execute
from agent.graph.guard import guard
from agent.graph.nudge import nudge
from agent.graph.routing import (
    route_after_execute,
    route_after_guard,
    route_after_model,
    route_after_nudge,
    route_entry,
)
from agent.state import AgentState


def build_graph():
    """Compile the loop. Call this again after editing a node or an edge."""
    graph = StateGraph(AgentState, context_schema=GraphContext)
    graph.add_node("call_model", call_model)
    graph.add_node("nudge", nudge)
    graph.add_node("guard", guard)
    graph.add_node("execute", execute)
    graph.add_conditional_edges(
        START, route_entry, {"call_model": "call_model", END: END}
    )
    graph.add_conditional_edges(
        "call_model",
        route_after_model,
        {"nudge": "nudge", "guard": "guard", END: END},
    )
    graph.add_conditional_edges(
        "nudge", route_after_nudge, {"call_model": "call_model", END: END}
    )
    graph.add_conditional_edges(
        "guard",
        route_after_guard,
        {"execute": "execute", "call_model": "call_model", END: END},
    )
    graph.add_conditional_edges(
        "execute", route_after_execute, {"call_model": "call_model", END: END}
    )
    return graph.compile()


async def run_graph(state: AgentState, context: GraphContext) -> dict:
    """Run one task. The recursion cap covers a few nodes per turn."""
    graph = build_graph()
    limit = context.max_turns * 4 + 5
    return await graph.ainvoke(
        state, context=context, config={"recursion_limit": limit}
    )
