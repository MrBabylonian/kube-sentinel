# pyright: reportAttributeAccessIssue=false
# pyright: reportPossiblyUnboundVariable=false
# pyright: reportOptionalMemberAccess=false

from typing import Any

import structlog
from kubernetes_asyncio import client  # type: ignore
from kubernetes_asyncio.client.rest import ApiException  # type: ignore

from kube_sentinel.k8s.client import K8sClient

logger = structlog.getLogger()


async def list_pods(namespace: str = "default") -> list[dict[str, Any]]:
    """
    List all pods in a namespace with their high-level status
    """
    k8s = K8sClient()
    api_client = await k8s.get_api_client()
    v1 = client.CoreV1Api(api_client)

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
        pod = await v1.read_namespaced_pod(
            name=pod_name, namespace=namespace, async_req=True
        )  # pyright: ignore

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
                state_msg = f"Waiting (Reason: {container_info.state.waiting.reason})"
            elif container_info.state.running:
                state_msg = "Running"

        report.append(
            f"Container: {container_info.name}, State: {state_msg if state_msg else 'N/A'} Restars: {container_info.restart_count}"
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
