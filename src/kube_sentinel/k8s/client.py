import structlog
from kubernetes import client, config
from kubernetes.client import ApiClient

logger = structlog.getLogger()


class K8sClient:
    """
    A Singleton wrapper for Kubernetes authentication.
    """

    _instance = None
    _api_client: ApiClient | None = None
    _core_v1_api: client.CoreV1Api | None = None
    _apps_v1_api: client.AppsV1Api | None = None

    def __new__(cls) -> "K8sClient":
        """
        Ensures only one instance of K8sClient exists.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_api_client(self) -> ApiClient:
        """
        Returns the active Kubernetes API client, initializing it if necessary.
        """

        if self._api_client is None:
            try:
                # STRATEGY 1: Local development
                config.load_kube_config()
                logger.info(
                    "auth_success", method="kube_config", context="local"
                )
            except config.ConfigException:
                try:
                    # STRATEGY 2: Production (In-cluster)
                    # When running as a Pod, K8s injects a Service Account token.
                    config.load_incluster_config()
                    logger.info(
                        "auth_success", method="in_cluster", context="remote"
                    )
                except config.ConfigException as error:
                    logger.exception("auth_failed", error=str(error))
                    raise
            self._api_client = client.ApiClient()
        return self._api_client

    @property
    def core_v1(self) -> client.CoreV1Api:
        """
        CoreV1 handles 'primitive' resources: Pods, Services, ConfigMaps, Secrets.
        """
        if self._core_v1_api is None:
            self._core_v1_api = client.CoreV1Api(self.get_api_client)
        return self._core_v1_api

    @property
    def apps_v1(self) -> client.AppsV1Api:
        """
        AppsV1 handles 'workload' resources: Deployments, StatefulSets, DaemonSets.
        """
        if self._apps_v1_api is None:
            self._apps_v1_api = client.AppsV1Api(self.get_api_client)
        return self._apps_v1_api
