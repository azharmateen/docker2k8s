"""Generate Kubernetes Ingress manifests."""

from typing import Any


class IngressGenerator:
    """Generate an Ingress manifest from a docker-compose service."""

    def __init__(
        self,
        service_name: str,
        service_config: dict[str, Any],
        namespace: str,
        provider_config: Any,
    ):
        self.name = service_name
        self.config = service_config
        self.namespace = namespace
        self.provider = provider_config

    def generate(self) -> dict:
        """Generate the Ingress manifest."""
        annotations = self._build_annotations()
        rules = self._build_rules()
        tls = self._build_tls()

        ingress = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": f"{self.name}-ingress",
                "namespace": self.namespace,
                "labels": {
                    "app": self.name,
                    "managed-by": "docker2k8s",
                },
                "annotations": annotations,
            },
            "spec": {
                "rules": rules,
            },
        }

        # Add ingressClassName based on provider
        ingress_class = self.provider.get_ingress_class()
        if ingress_class:
            ingress["spec"]["ingressClassName"] = ingress_class

        if tls:
            ingress["spec"]["tls"] = tls

        return ingress

    def _build_annotations(self) -> dict:
        """Build ingress annotations based on provider and config."""
        annotations = {
            "docker2k8s/generated": "true",
        }

        # Provider-specific annotations
        provider_annotations = self.provider.get_ingress_annotations()
        annotations.update(provider_annotations)

        # Parse labels for custom annotations
        labels = self.config.get("labels", {})
        if isinstance(labels, dict):
            for key, value in labels.items():
                if key.startswith("traefik."):
                    # Convert Traefik docker labels to K8s annotations
                    annotations[key] = value
                elif key.startswith("nginx."):
                    annotations[key] = value

        return annotations

    def _build_rules(self) -> list[dict]:
        """Build ingress rules."""
        rules = []
        host = self._get_host()
        paths = self._build_paths()

        rule = {"http": {"paths": paths}}
        if host:
            rule["host"] = host

        rules.append(rule)
        return rules

    def _build_paths(self) -> list[dict]:
        """Build ingress paths from service ports."""
        paths = []
        ports = self.config.get("ports", [])

        # Use the first HTTP-like port
        http_ports = [p for p in ports if p["container_port"] in (80, 443, 8080, 8443, 3000, 5000, 9000)]
        target_ports = http_ports if http_ports else ports[:1]

        for p in target_ports:
            paths.append({
                "path": "/",
                "pathType": "Prefix",
                "backend": {
                    "service": {
                        "name": f"{self.name}-service",
                        "port": {
                            "number": p.get("host_port") or p["container_port"],
                        },
                    },
                },
            })

        return paths

    def _get_host(self) -> str | None:
        """Extract host from labels or generate a default."""
        labels = self.config.get("labels", {})
        if isinstance(labels, dict):
            # Check for explicit host label
            host = labels.get("docker2k8s.ingress.host")
            if host:
                return host

            # Check Traefik-style host rule
            for key, value in labels.items():
                if "rule" in key and "Host" in str(value):
                    import re
                    match = re.search(r"Host\(`([^`]+)`\)", str(value))
                    if match:
                        return match.group(1)

        # Default: service-name.local
        return f"{self.name}.local"

    def _build_tls(self) -> list[dict] | None:
        """Build TLS configuration if HTTPS ports are present."""
        labels = self.config.get("labels", {})
        if isinstance(labels, dict):
            tls_enabled = labels.get("docker2k8s.ingress.tls", "false")
            if tls_enabled.lower() == "true":
                host = self._get_host()
                return [{
                    "hosts": [host] if host else [],
                    "secretName": f"{self.name}-tls",
                }]

        # Auto-enable TLS if port 443 is exposed
        for p in self.config.get("ports", []):
            if p["container_port"] == 443:
                host = self._get_host()
                return [{
                    "hosts": [host] if host else [],
                    "secretName": f"{self.name}-tls",
                }]

        return None
