from typing import Any

import structlog
from kubernetes.client.rest import ApiException

from kube_sentinel.k8s.client import K8sClient

logger = structlog.getLogger()


def list_pods(namespace: str = "default") -> list[dict[str, Any]]:
    """
    List all pods in a namespace with their high-level status
    """
    v1 = K8sClient().core_v1
    try:
        pods = v1.list_namespaced_pod(namespace)  # type: ignore[no-untyped-call]
        results = []
        for p in pods.items:
            # Safety check: newly created pods might not have
            # container statuses yet
            restarts = 0
            if p.status.container_statuses:
                restarts = sum(
                    c.restart_count for c in p.status.container_statuses
                )

            results.append(
                {
                    "name": p.metadata.name,
                    "status": p.status.phase,
                    "restarts": restarts,
                    # Returning only 'False' conditions to save token space
                    "conditions": [
                        c.reason
                        for c in p.status.conditions
                        if c.status == "False"
                    ],
                }
            )
        return results
    except ApiException as error:
        logger.error("list_pods_failed", error=str(error))
        return [{"error": str(error)}]


def get_pod_logs(pod_name: str, namespace: str = "default") -> str:
    """
    Retrieve logs.
    """
    v1 = K8sClient().core_v1
    try:
        return str(
            v1.read_namespaced_pod_log(  # type: ignore[no-untyped-call]
                name=pod_name, namespace=namespace, tail_lines=50
            )
        )
    except ApiException as e:
        logger.exception("get_pod_logs_failed", pod=pod_name, error=str(e))
        return f"Error reading logs: {e}"

def patch_deployment_resources(
    deployment_name: str,
    namespace: str,
    container_name: str,
    limit_memory: str,
    request_memory: str
)-> str:
    """
    
    """
