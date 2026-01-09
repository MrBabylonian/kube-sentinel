import json
import os
from typing import Any

import structlog
from dotenv import load_dotenv
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables.base import Runnable
from langchain_core.tools import tool
from langchain_core.tools.base import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI

from kube_sentinel.domain.schemas import (
    Diagnosis,
    RemediationPlan,
    SreAgentState,
)
from kube_sentinel.k8s.tools import (
    describe_pod,
    get_deployment_details,
    get_pod_logs,
    list_pods,
    patch_deployment,
)

load_dotenv()

GOOGLE_VERTEX_API_KEY: str | None = os.getenv("GOOGLE_VERTEX_API_KEY")
GOOGLE_CLOUD_PROJECT: str | None = os.getenv("GOOGLE_CLOUD_PROJECT")

if not GOOGLE_VERTEX_API_KEY or not GOOGLE_CLOUD_PROJECT:
    raise ValueError(
        "GOOGLE_VERTEX_API_KEY and GOOGLE_CLOUD_PROJECT "
        "must be set in environment variables."
    )


logger = structlog.get_logger()


@tool
async def list_cluster_pods(namespace: str) -> list[dict[str, Any]]:
    """
    List pods to check status
    """
    return await list_pods(namespace)


@tool
async def describe_cluster_pod(pod_name: str, namespace: str) -> str:
    """Get pod details (events, exit codes)."""
    return await describe_pod(pod_name=pod_name, namespace=namespace)


@tool
async def get_cluster_pod_logs(pod_name: str, namespace: str) -> str:
    """Get logs."""
    return await get_pod_logs(pod_name, namespace)


@tool
async def get_deployment_spec(
    deployment_name: str, namespace: str
) -> dict[str, Any]:
    """Get the current JSON configuration of a Deployment.
    CRITICAL: You must call this before generating a patch to see current limits/env."""
    return await get_deployment_details(deployment_name, namespace)


READ_TOOLS: list[BaseTool] = [
    list_cluster_pods,
    describe_cluster_pod,
    get_cluster_pod_logs,
    get_deployment_spec,
]

llm = ChatGoogleGenerativeAI(
    model="gemini-3-pro-preview",
    temperature=0,
    api_key=GOOGLE_VERTEX_API_KEY,
    project=GOOGLE_CLOUD_PROJECT,
    vertexai=True,
)


async def agent_node(state: SreAgentState) -> dict[str, list[Any]]:
    """
    The Autonomous Brain.
    It decides whether to call a READ tool (explore) or generate a
    (RemediationPlan Tool).
    """
    # Defensive checks for state structure
    messages = state.get("messages")
    if not messages or not isinstance(messages, list):
        logger.error(
            "agent_node_invalid_state",
            error="messages not found or not a list",
        )
        raise ValueError("Invalid state: messages field missing or not a list")

    namespace = state.get("namespace")
    if not namespace or not isinstance(namespace, str):
        logger.error(
            "agent_node_invalid_state",
            error="namespace not found or not a string",
        )
        raise ValueError(
            "Invalid state: namespace field missing or not a string"
        )

    logger.info("agent_reasoning", history_len=len(messages))
    # We bind the Read Tools AND the RemediationPlan structure.
    # We treat RemediationPlan as a tool call so the LLM can "call" it to signal completion.

    llm_with_tools: Runnable[LanguageModelInput, AIMessage] = llm.bind_tools(
        READ_TOOLS + [Diagnosis, RemediationPlan]
    )

    system_prompt = f"""
    You are KubeSentinel, an expert autonomous SRE (Site Reliabiliy Engineer)
        Your goal is to identify and fix issues in the '{namespace}'
        namespace.

    PROTOCOL:
    1. EXPLORE: Use read tools to find the root cause.
    2. DIAGNOSE: When you find the issue, call the 'Diagnosis' tool to record
    it.
    3. VERIFY: Before fixing, call 'get_deployment_spec' to see current config.
    4. SOLVE: Call the 'RemediationPlan' tool with a valid JSON Merge Patch.

    FEEDBACK:
    If a patch failed validation, the error is in the history. Fix your JSON.
"""

    response: AIMessage = await llm_with_tools.ainvoke(
        input=[SystemMessage(content=system_prompt)] + state["messages"]
    )

    return {"messages": [response]}


async def validate_node(state: SreAgentState) -> dict[str, Any]:
    """
    The Gatekeeper.
    Extracts the plan, runs a Dry Run, and reports success/failure.
    """
    # Defensive checks for state structure
    messages = state.get("messages")
    if not messages or not isinstance(messages, list):
        logger.error(
            "validate_node_invalid_state",
            error="messages_not_found_or_not_a_list",
        )
        raise ValueError("Invalid state: messages field missing or not a list")

    if len(messages) == 0:
        logger.error(
            "validate_node_empty_messages", error="no_messages_in_state"
        )
        raise ValueError("Invalid state: messages list is empty")

    last_message = messages[-1]  # last message from agent

    # Check if last_message has tool_calls attribute
    tool_calls = getattr(last_message, "tool_calls", None)
    if tool_calls is None:
        logger.error(
            "validate_node_no_tool_calls",
            error="last message has no tool_calls",
        )
        raise ValueError("Invalid message: no tool_calls attribute found")

    if not tool_calls or not isinstance(tool_calls, (list, tuple)):
        logger.error(
            "validate_node_invalid_tool_calls",
            error="tool_calls is empty or not a sequence",
        )
        raise ValueError("Invalid tool_calls: empty or not a sequence")

    # Get first tool call and check if it has args
    tool_call = tool_calls[0]
    if not hasattr(tool_call, "args") and not isinstance(tool_call, dict):
        logger.error("validate_node_no_args", error="tool_call has no args")
        raise ValueError("Invalid tool_call: no args attribute found")

    # Get args safely
    args = (
        tool_call.get("args")
        if isinstance(tool_call, dict)
        else getattr(tool_call, "args", None)
    )
    if args is None:
        logger.error("validate_node_args_none", error="tool_call args is None")
        raise ValueError("Invalid tool_call: args is None")

    # Converting args to Pydantic model
    try:
        plan = RemediationPlan(**args)
    except Exception as e:
        logger.error("validate_node_pydantic_error", error=str(e), args=args)
        raise ValueError(f"Failed to create RemediationPlan from args: {e}")

    logger.info(
        "validating_plan",
        resource=plan.resource_name,
        patch=json.dumps(plan.patch_json, indent=2),
    )

    result = await patch_deployment(
        deployment_name=plan.resource_name,
        namespace=plan.namespace,
        patch_json=plan.patch_json,
        dry_run=True,
    )

    if "Dry run successful" in result:
        logger.info("dry_run_passed")
        return {
            "remediation_plan": plan,  # To save the plan in state
            "dry_run_passed": True,
            "messages": [
                AIMessage(content=f"SYSTEM: Dry run passed. {result}")
            ],
        }
    else:
        logger.warning("dry_run_failed", result=result)
        return {
            "remediation_plan": plan,
            "dry_run_passed": False,
            "messages": [
                AIMessage(content=f"SYSTEM: Dry run failed. {result}")
            ],
        }


async def remediate_node(state: SreAgentState) -> dict[str, list[AIMessage]]:
    """The Executioner."""

    if not state.get("remediation_plan"):
        logger.error(
            "remediate_node_no_plan", error="no remediation_plan in state"
        )
        raise ValueError("No remediation_plan found in state")

    # Validate dry-run passed before executing remediation
    if not state.get("dry_run_passed"):
        logger.error(
            "remediate_node_dry_run_not_passed",
            error="dry_run_did_not_pass",
        )
        raise ValueError(
            "Cannot execute remediation: dry-run validation failed"
        )

    # Validate user approval before executing remediation
    if not state.get("user_approval"):
        logger.error(
            "remediate_node_user_approval_missing",
            error="user_approval_not_granted",
        )
        raise ValueError("Cannot execute remediation: user approval required")

    plan: RemediationPlan = state["remediation_plan"]  # type: ignore

    logger.info("executing_fix", resource=plan.resource_name)

    result = await patch_deployment(
        deployment_name=plan.resource_name,
        namespace=plan.namespace,
        patch_json=plan.patch_json,
        dry_run=False,
    )
    return {
        "messages": [
            AIMessage(content=f"SYSTEM: Remediation executed. {result}")
        ]
    }
