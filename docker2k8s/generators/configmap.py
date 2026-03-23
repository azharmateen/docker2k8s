"""Generate Kubernetes ConfigMap manifests."""


class ConfigMapGenerator:
    """Generate a ConfigMap manifest from docker-compose environment variables."""

    def __init__(
        self,
        service_name: str,
        config_vars: dict[str, str],
        namespace: str,
    ):
        self.name = service_name
        self.config_vars = config_vars
        self.namespace = namespace

    def generate(self) -> dict:
        """Generate the ConfigMap manifest."""
        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": f"{self.name}-configmap",
                "namespace": self.namespace,
                "labels": {
                    "app": self.name,
                    "managed-by": "docker2k8s",
                },
            },
            "data": {k: str(v) for k, v in self.config_vars.items()},
        }
