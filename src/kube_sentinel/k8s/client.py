import structlog
from kubernetes_asyncio import client, config  # type: ignore
from kubernetes_asyncio.client import ApiClient  # type: ignore

logger = structlog.getLogger()


class K8sClient:
    """
    Async singleton wrapper for Kubernetes authentication.
    """

    # Constructors (__init__) cannot be async.
    # So I use a lazy-loading pattern in 'get_api_client'

    _instance = None
    _api_client: ApiClient | None = None

    def __new__(cls) -> "K8sClient":
        """
        Ensures only one instance of K8sClient exists.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_api_client(self) -> ApiClient:
        """
        Returns the active Kubernetes API client, initializing it if necessary.
        """

        if self._api_client is None:
            try:
                # STRATEGY 1: Local development
                await config.load_kube_config()  # (async load)
                logger.info(
                    "auth_success", method="kube_config", context="local"
                )
            except config.ConfigException:
                try:
                    # STRATEGY 2: Production (In-cluster)
                    # When running as a Pod
                    # K8s injects a Service Account token.
                    config.load_incluster_config()  # sync load. I/O blocking.
                    logger.info(
                        "auth_success", method="in_cluster", context="remote"
                    )
                except config.ConfigException as error:
                    logger.exception("auth_failed", error=str(error))
                    raise
                except Exception as error:
                    logger.exception(
                        "k8s_auth_unexpected_error", error=str(error)
                    )
                    raise
            self._api_client = client.ApiClient()
        return self._api_client

    async def close(self) -> None:
        """
        Manually close the API client and reset the singleton.
        """
        if self._api_client:
            await self._api_client.close()
            self._api_client = None
        self._instance = None