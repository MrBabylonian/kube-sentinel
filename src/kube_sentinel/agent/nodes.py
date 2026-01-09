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
    """
    # Defensive checks for state structure
    messages = state.get("messages")
    # Allow empty list (though main.py should prevent this), reject None
    if messages is None or not isinstance(messages, list):
        logger.error(
            "agent_node_invalid_state",
            error="messages field missing or not a list",
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

    llm_with_tools: Runnable[LanguageModelInput, AIMessage] = llm.bind_tools(
        READ_TOOLS + [Diagnosis, RemediationPlan]
    )

    system_prompt = f"""
    You are KubeSentinel, an expert autonomous SRE (Site Reliabiliy Engineer)
    Your goal is to identify and fix issues in the '{namespace}' namespace.

    PROTOCOL:
    1. EXPLORE: Use read tools to find the root cause.
    2. DIAGNOSE: When you find the issue, call the 'Diagnosis' tool to record it.
    3. VERIFY: Before fixing, call 'get_deployment_spec' to see current config.
    4. SOLVE: Call the 'RemediationPlan' tool with a valid JSON Merge Patch.

    FEEDBACK:
    If a patch failed validation, the error is in the history. Fix your JSON.
    """

    # We prepend the System Prompt to the conversation history
    # main.py guarantees that 'messages' starts with a HumanMessage
    response: AIMessage = await llm_with_tools.ainvoke(
        input=[SystemMessage(content=system_prompt)] + messages
    )

    return {"messages": [response]}


async def validate_node(state: SreAgentState) -> dict[str, Any]:
    """
    The Gatekeeper.
    Extracts the plan, runs a Dry Run, and reports success/failure.
    """
    messages = state.get("messages")
    if messages is None or not isinstance(messages, list):
        raise ValueError("Invalid state: messages field missing or not a list")

    if len(messages) == 0:
        raise ValueError("Invalid state: messages list is empty")

    last_message = messages[-1]

    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls or not isinstance(tool_calls, (list, tuple)):
        raise ValueError("Invalid message: no tool_calls found")

    tool_call = tool_calls[0]

    # Safe args extraction
    args = None
    if isinstance(tool_call, dict):
        args = tool_call.get("args")
    else:
        args = getattr(tool_call, "args", None)

    if args is None:
        raise ValueError("Invalid tool_call: args is None")

    try:
        plan = RemediationPlan(**args)
    except Exception as e:
        raise ValueError(f"Failed to create RemediationPlan: {e}")

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
            "remediation_plan": plan,
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
        raise ValueError("No remediation_plan found in state")

    if not state.get("dry_run_passed"):
        raise ValueError("Cannot execute: dry-run validation failed")

    if not state.get("user_approval"):
        raise ValueError("Cannot execute: user approval required")

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
