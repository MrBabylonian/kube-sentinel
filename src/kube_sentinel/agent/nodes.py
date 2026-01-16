import asyncio
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


    POST-REMEDIATION:
    If you receive VERIFICATION FAILED message, analyze the new state carefully.
    Do NOT retry the exact same fix. Adjust your strategy based on the feedback.
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
    except Exception as error:
        raise ValueError(f"Failed to create RemediationPlan: {error}")

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


async def verify_fix_node(state: SreAgentState) -> dict[str, Any]:
    """
    Verifies that the remediation actually resolved the issue.

    Theoretical Concepts:
    - Feedback Control System: Measures output (pod health) and to setpoint
    - Eventual Consistency: Kubernetes changes propagate over time, so we poll with backoff
    - Circuit Breaker: Prevents infinite retry loops with attempt counter

    Implementation Strategy:
    1. Wait for kubernetes to propagate changes (exponential backoff)
    2. Re-query the resource that was problematic
    3. Check if the issue is resolved
    4.Return success OR detailed feedback to the agent
    """
    namespace = state.get("namespace", "default")
    diagnosis = state.get("diagnosis")
    remediation_plan = state.get("remediation_plan")
    current_attempts = state.get("verification_attempts", 0)

    # Ensure we have the context we need
    if not diagnosis or not remediation_plan:
        logger.error("missing_context_during_verification")
        return {
            "messages": [
                SystemMessage(
                    content="VERIFICATION ERROR: Missing diagnosis or remediation plan in state."
                )
            ]
        }

    target_resource = diagnosis.affected_resource

    logger.info(
        "verification_starting",
        resource=target_resource,
        attempt=current_attempts + 1,
    )

    # ============================================================
    # Step 1: Wait for Kubernetes Propagation
    # ============================================================
    # Kubernetes is eventually consistent. After a patch:
    # - ReplicaSet needs to be created
    # - Scheduler needs to place pods
    # - Kubelet needs to pull images and start containers
    # - This can take 5-30 seconds depending on cluster load

    wait_time = min(
        5 * (2**current_attempts), 30
    )  # Exponential backoff: 5s, 10s, 20s, max 30s

    logger.info("waiting_for_propagation", seconds=wait_time)

    await asyncio.sleep(wait_time)

    # ============================================================
    # Step 2: Re-Query Resource Status
    # ============================================================
    # We'll list all pods controlled by the deployment and check their states

    try:
        pods = await list_pods(namespace)

        # Filter for pods belonging to our deployment
        # Pod names typically follow pattern: <deployment-name>-<replicaset-hash>-<pod-hash>
        relevant_pods = [
            pod
            for pod in pods
            if pod.get("name", "").startswith(
                target_resource.replace("-deployment", "")
            )
        ]

        if not relevant_pods:
            failure_msg = (
                f"VERIFICATION_FAILED: No pods found for {target_resource}"
            )
            logger.warning(
                "no_pods_found_during_verification", resource=target_resource
            )

        # ============================================================
        # Step 3: Health Check Logic
        # ============================================================
        # Define what "healthy" means:
        # - Phase should be "Running"
        # - Ready status should be True
        # - No CrashLoopBackOff, ImagePullBackOff, OOMKilled, etc.
        unhealthy_pods = []
        for pod in relevant_pods:
            # "status" field from list_pods contains the pod phase
            phase = pod.get("status", "Unknown")
            # "conditions" contains reasons for conditions with status == "False"
            # If empty, the pod is considered ready (no failing conditions)
            conditions = pod.get("conditions", [])
            ready = len(conditions) == 0

            # Check for BackOff/Error in conditions list
            has_backoff_or_error = any(
                "BackOff" in cond or "Error" in cond for cond in conditions
            )

            if phase != "Running" or not ready or has_backoff_or_error:
                unhealthy_pods.append(
                    {
                        "name": pod.get("name"),
                        "phase": phase,
                        "conditions": conditions,
                        "ready": ready,
                    }
                )
        # ============================================================
        # Step 4: Decision Logic
        # ============================================================
        if not unhealthy_pods:
            success_msg = (
                f"✅ VERIFICATION SUCCESS: All pods for {target_resource} "
                f"are now healthy (Running & Ready). Issue resolved."
            )
            logger.info(
                "verification_success",
                resource=target_resource,
                pod_count=len(relevant_pods),
            )
            return {
                "verification_attempts": 0,  # Reset counter for future issues
                "last_verification_result": success_msg,
                "messages": [SystemMessage(content=success_msg)],
            }
        else:
            # FAILURE: Some pods are still unhealthy

            MAX_VERIFICATION_ATTEMPTS = 3

            if current_attempts >= MAX_VERIFICATION_ATTEMPTS:
                failure_msg = (
                    f"❌ VERIFICATION FAILED: Max attempts ({MAX_VERIFICATION_ATTEMPTS}) reached. "
                    f"Pods still unhealthy: {json.dumps(unhealthy_pods, indent=2)}. "
                    f"Manual intervention required. The automated remediation did not resolve the issue."
                )
                logger.error(
                    "verification_max_attempts",
                    resource=target_resource,
                    unhealthy_pods=unhealthy_pods,
                )
                return {
                    "verification_attempts": current_attempts * 1,
                    "last_verification_result": failure_msg,
                    "messages": [SystemMessage(content=failure_msg)],
                }
            else:
                # Retry: Give agent detailed feedback to adjust strategy
                failure_msg = (
                    f"⚠️ VERIFICATION FAILED (Attempt {current_attempts + 1}/{MAX_VERIFICATION_ATTEMPTS}): "
                    f"Some pods for {target_resource} are still unhealthy: "
                    f"{json.dumps(unhealthy_pods, indent=2)}. "
                    f"IMPORTANT: Do NOT retry the same fix. Analyze the new state and try a DIFFERENT approach. "
                    f"Consider: 1) Increasing resource limits further, 2) Changing environment variables, "
                    f"3) Checking for application-level bugs."
                )
                logger.warning(
                    "verification_retry",
                    resource=target_resource,
                    attempt=current_attempts + 1,
                    unhealthy_pods=unhealthy_pods,
                )
                return {
                    "verification_attempts": current_attempts + 1,
                    "last_verification_result": failure_msg,
                    "messages": [SystemMessage(content=failure_msg)],
                }
    except Exception as error:
        error_msg = (
            f"VERIFICATION ERROR: Exception during health check: {str(error)}"
        )
        logger.exception("verification_exception", resource=target_resource)
        return {
            "verification_attempts": current_attempts + 1,
            "last_verification_result": error_msg,
            "messages": [SystemMessage(content=error_msg)],
        }
