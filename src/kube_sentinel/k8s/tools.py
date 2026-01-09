# pyright: reportAttributeAccessIssue=false
# pyright: reportPossiblyUnboundVariable=false
# pyright: reportOptionalMemberAccess=false

import json
from typing import Any, Literal

import structlog
from kubernetes_asyncio import client  # type: ignore
from kubernetes_asyncio.client.api_client import ApiClient
from kubernetes_asyncio.client.rest import ApiException  # type: ignore

from kube_sentinel.k8s.client import K8sClient

logger = structlog.getLogger()


async def list_pods(namespace: str = "default") -> list[dict[str, Any]]:
    """
    List all pods in a namespace with their high-level status
    """
    k8s = K8sClient()
    api_client: ApiClient = await k8s.get_api_client()
    v1 = client.CoreV1Api(api_client=api_client)

    logger.debug("listing_pods", namespace=namespace)
    try:
        pods: client.V1PodList = await v1.list_namespaced_pod(namespace)
        results = []
        if pods.items:
            for pod in pods.items:
                # Safety check: newly created pods might not have
                # container statuses yet
                restarts = 0
                if pod.status.container_statuses:
                    restarts = sum(
                        c.restart_count for c in pod.status.container_statuses
                    )
                else:
                    logger.debug(
                        "pod_no_container_statuses",
                        pod_name=pod.metadata.name,
                        namespace=namespace,
                    )
                results.append(
                    {
                        "name": pod.metadata.name,
                        "status": pod.status.phase,
                        "restarts": restarts,
                        # Returning only 'False' conditions to save token space
                        "conditions": [
                            condition.reason
                            for condition in pod.status.conditions
                            if condition.status == "False"
                        ]
                        if pod.status.conditions
                        else [],
                    }
                )
        else:
            logger.info("no_pods_found", namespace=namespace)
        return results
    except ApiException as error:
        logger.error("list_pods_failed", error=str(error))
        return [{"error": str(error)}]
    except Exception as error:
        logger.exception("list_pods_unexpected_error", error=str(error))
        return [{"error": str(error)}]


async def describe_pod(pod_name: str, namespace: str = "default") -> str:
    """
    Get detailed status (Non blocking)
    """
    k8s = K8sClient()
    api_client = await k8s.get_api_client()
    v1 = client.CoreV1Api(api_client)

    logger.info("describing_pod", pod_name=pod_name, namespace=namespace)

    try:
        pod = await v1.read_namespaced_pod(name=pod_name, namespace=namespace)  # pyright: ignore

        statuses = (
            pod.status.container_statuses
            if pod.status.container_statuses
            else []
        )
        report = []

        for container_info in statuses:
            state_msg = "Unknown"
            if container_info.state.terminated:
                state_msg = f"Terminated (Reason: {container_info.state.terminated.reason}, Exit Code: {container_info.state.terminated.exit_code})"  # noqa: E501
            elif container_info.state.waiting:
                state_msg = (
                    f"Waiting (Reason: {container_info.state.waiting.reason})"
                )
            elif container_info.state.running:
                state_msg = "Running"

            report.append(
                f"Container: {container_info.name}, State: {state_msg if state_msg else 'N/A'} Restarts: {container_info.restart_count}"  # noqa : E501
            )

        return "\n".join(report)
    except ApiException as error:
        logger.error("describe_pod_failed", error=str(error))
        return f"Error describing pod: {error}"
    except Exception as error:
        logger.exception("describe_pod_unexpected_error", error=str(error))
        return f"Unexpected error: {error}"


async def get_pod_logs(pod_name: str, namespace: str = "default") -> str:
    """Retrieve logs (Non-blocking)."""
    k8s = K8sClient()
    api_client = await k8s.get_api_client()
    v1 = client.CoreV1Api(api_client)

    try:
        logs = await v1.read_namespaced_pod_log(
            name=pod_name, namespace=namespace, tail_lines=50
        )

        return str(logs)
    except ApiException as error:
        return f"Error reading logs: {error}"
    except Exception as error:
        logger.exception("get_pod_logs_unexpected_error", error=str(error))
        return f"Unexpected error: {error}"


async def get_deployment_details(
    deployment_name: str, namespace: str
) -> dict[str, Any]:
    """
    Get the configuration of a Deployment.
    """
    k8s = K8sClient()
    api_client = await k8s.get_api_client()
    apps_v1 = client.AppsV1Api(api_client)

    try:
        deployment = await apps_v1.read_namespaced_deployment(
            deployment_name, namespace
        )  # pyright: ignore

        # We parse the complex object into a clean dictionary for the LLM
        containers = []
        for container in deployment.spec.template.spec.containers:
            # Safely convert resources (requests/limits) to dict
            resources = (
                container.resources.to_dict() if container.resources else {}
            )

            containers.append(
                {
                    "name": container.name,
                    "image": container.image,
                    "resources": resources,
                    "env": [env.to_dict() for env in container.env]
                    if container.env
                    else [],
                }
            )

        return {
            "kind": "Deployment",
            "name": deployment_name,
            "containers": containers,
        }
    except ApiException as e:
        logger.error("get_deployment_failed", error=str(e))
        return {"error": str(e)}
    except Exception as error:
        logger.exception(
            "get_deployment_details_unexpected_error", error=str(error)
        )
        return {"error": str(error)}


async def patch_deployment(
    deployment_name: str,
    namespace: str,
    patch_json: dict[str, Any],
    dry_run: bool = False,
) -> str:
    """
    Apply a JSON merge patch to a deployment.


    This is the "Flight Simulator" mode.
    If dry_run=True, we send the request to Kubernetes with dry_run="All".
    The API Server runs:
      1. Authentication
      2. Schema Validation (Is the JSON valid?)
      3. Admission Controllers (Is this allowed?)

    If any fail, we get an error. If they pass, we get success,
    BUT the cluster state is NOT changed.
    """
    k8s = K8sClient()
    api_client = await k8s.get_api_client()
    apps_v1 = client.AppsV1Api(api_client)

    dry_run_arg: None | Literal["All"] = "All" if dry_run else None

    log_event = (
        "patching_deployment_dry_run"
        if dry_run
        else "patching_deployment_execute"
    )

    logger.info(
        log_event,
        deployment=deployment_name,
        patch=json.dumps(patch_json, indent=2),
    )

    try:
        # The agent is responsible for
        # constructing the correct nested structure

        await apps_v1.patch_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
            body=patch_json,
            dry_run=dry_run_arg,
        )  # pyright: ignore

        if dry_run:
            return "Dry run successful: Patch is valid and can be applied."
        else:
            return "Patch applied successfully."

    except ApiException as error:
        logger.error("patch_deployment_failed", error=str(error))
        return f"Error patching deployment: {error}"
    except Exception as error:
        logger.exception("patch_deployment_unexpected_error", error=str(error))
        return f"Unexpected error: {error}"
