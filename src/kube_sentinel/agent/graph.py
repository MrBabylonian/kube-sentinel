from typing import Any, Literal

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.prebuilt.tool_node import ToolNode

from kube_sentinel.agent.nodes import (
    READ_TOOLS,
    agent_node,
    remediate_node,
    validate_node,
)
from kube_sentinel.domain.schemas import Diagnosis, SreAgentState

logger = structlog.getLogger()


"""
These are pure logic. They look at the state dictionary and return a string
(e.g., "continue" or "stop"). 
Since they run in microseconds and don't touch the network,
making them async adds unnecessary overhead (scheduler switching costs).
"""


def route_agent_action(
    state: SreAgentState,
) -> Literal["tools", "validate", "end"]:
    """
    Decide next step based on the Agent's output.
    """
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last_message = messages[-1]

    # 1. Check if the agent wants to call a tool
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        # If no tool calls, the agent is just chatting or finished.
        # In a strict loop, this might be an error, but I'll end for safety.
        return "end"

    # 2. Inspect the tool name
    # Note: Depending on the LLM, it might queue multiple calls.
    # I look at the first one to decide the "Phase".
    tool_call = last_message.tool_calls[0]
    try:
        tool_name = tool_call.get("name")
    except AttributeError:
        tool_name = getattr(tool_call, "name", None)

    if tool_name == "RemediationPlan":
        return "validate"

    # If it's Diagnosis, I treat it as a tool call that returns data,
    # so I route to "tools"
    # Since I am bounding Diagnosis as a tool, ToolNode will handle it
    # (returning the validation result of the Pydantic model).

    return "tools"


def check_validation(state: SreAgentState) -> Literal["approve", "agent"]:
    """
    - Passed? -> Go to Human Approval (Main loop intercepts this)
    - Failed? -> Go back to Agent to fix
    """
    if state.get("dry_run_passed"):
        return "approve"

    return "agent"


def build_graph() -> CompiledStateGraph[Any]:
    """
    Constructs the Async State Graph.
    """
    workflow = StateGraph(SreAgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("remediate", remediate_node)

    all_tools = READ_TOOLS + [Diagnosis]
    workflow.add_node("tools", ToolNode(tools=all_tools))

    workflow.set_entry_point("agent")

    # Agent Routing (Agent -> Tools OR Validate)
    workflow.add_conditional_edges(
        source="agent",
        path=route_agent_action,
        path_map={"tools": "tools", "validate": "validate", "end": END},
    )

    # Tool Loop (Tools -> Agent)
    # After a tool runs (including Diagnosis), go back to Agent to think.
    workflow.add_edge("tools", "agent")

    # Validation Routing (Validate -> Approve OR Agent)
    workflow.add_conditional_edges(
        source="validate",
        path=check_validation,
        path_map={
            "approve": "remediate",  # Passed? Execute (Main loop intercepts)
            "agent": "agent",  # Failed? Fix it
        },
    )

    workflow.add_edge(start_key="remediate", end_key=END)

    memory = MemorySaver()

    return workflow.compile(checkpointer=memory)
