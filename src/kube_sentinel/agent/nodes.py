import json
import os
from typing import Any

import structlog
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_core.tools.base import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI

from kube_sentinel.domain.schemas import (
    Diagnosis,
    RemediationPlan,
    SreAgentState,
)
from kube_sentinel.k8s.tools import patch_deployment

load_dotenv()

GOOGLE_VERTEX_API_KEY = os.getenv("GOOGLE_VERTEX_API_KEY")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

if not GOOGLE_VERTEX_API_KEY or not GOOGLE_CLOUD_PROJECT:
    raise ValueError(
        "GOOGLE_VERTEX_API_KEY and GOOGLE_CLOUD_PROJECT "
        "must be set in environment variables."
    )

from kube_sentinel.k8s.tools import (
    describe_pod,
    get_deployment_details,
    get_pod_logs,
    list_pods,
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
    It decides whether to call a READ tool (explore) or generate a RemediationPlan (solve).
    """
    logger.info("agent_reasoning", history_len=len(state["messages"]))
    # We bind the Read Tools AND the RemediationPlan structure.
    # We treat RemediationPlan as a tool call so the LLM can "call" it to signal completion.

    llm_with_tools = llm.bind_tools(READ_TOOLS + [Diagnosis, RemediationPlan])

    system_prompt = """
    You are KubeSentinel, an expert autonomous SRE (Site Reliabiliy Engineer)
        Your goal is to identify and fix issues in the '{state['namespace']}'
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

    response = await llm_with_tools.invoke(
        [SystemMessage(content=system_prompt)] + state["messages"]
    )  # type: ignore

    return {"messages": [response]}


async def validate_node(state: SreAgentState) -> dict[str, Any]:
    """
    The Gatekeeper.
    Extracts the plan, runs a Dry Run, and reports success/failure.
    """
    last_message = state["messages"][-1]  # last message from agent
    tool_call = last_message.tool_calls[0]  # first tool call

    # Converting args to Pydantic model
    plan = RemediationPlan(**tool_call["args"])

    logger.info(
        "validating_plan",
        resoure=plan.resource_name,
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
            "messages": [AIMessage(f"SYSTEM: Dry run passed. {result}")],
        }
    else:
        logger.warning("dry_run_failed", result=result)
        return {
            "remediation_plan": plan,
            "dry_run_passed": False,
            "messages": [AIMessage(f"SYSTEM: Dry run failed. {result}")],
        }
