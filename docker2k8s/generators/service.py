"""Generate Kubernetes Service manifests."""

from typing import Any


class ServiceGenerator:
    """Generate a Service manifest from a docker-compose service."""

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
        """Generate the Service manifest."""
        ports = self._build_ports()
        service_type = self._determine_service_type()

        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"{self.name}-service",
                "namespace": self.namespace,
                "labels": {
                    "app": self.name,
                    "managed-by": "docker2k8s",
                },
            },
            "spec": {
                "selector": {
                    "app": self.name,
                },
                "type": service_type,
                "ports": ports,
            },
        }

        # Provider-specific annotations (e.g., AWS NLB, GKE internal LB)
        annotations = self.provider.get_service_annotations(service_type)
        if annotations:
            service["metadata"]["annotations"] = annotations

        return service

    def _build_ports(self) -> list[dict]:
        """Build service port specifications."""
        ports = []
        seen = set()

        for idx, p in enumerate(self.config.get("ports", [])):
            container_port = p["container_port"]
            host_port = p.get("host_port") or container_port
            protocol = p.get("protocol", "tcp").upper()

            # Avoid duplicate ports
            key = (container_port, protocol)
            if key in seen:
                continue
            seen.add(key)

            port_spec = {
                "name": self._port_name(container_port, protocol, idx),
                "port": host_port,
                "targetPort": container_port,
                "protocol": protocol,
            }

            # Add nodePort for NodePort services
            if self._determine_service_type() == "NodePort" and host_port >= 30000:
                port_spec["nodePort"] = host_port

            ports.append(port_spec)

        return ports

    def _determine_service_type(self) -> str:
        """Determine the Kubernetes Service type based on port configuration.

        Rules:
        - If any port has host_ip = 0.0.0.0 or is explicitly exposed -> LoadBalancer
        - If any port has a host_port >= 30000 -> NodePort
        - If ports only define container_port -> ClusterIP
        - Default: ClusterIP
        """
        labels = self.config.get("labels", {})

        # Check for explicit label override
        if isinstance(labels, dict):
            svc_type = labels.get("docker2k8s.service.type", "")
            if svc_type in ("ClusterIP", "NodePort", "LoadBalancer"):
                return svc_type

        for p in self.config.get("ports", []):
            host_port = p.get("host_port")
            host_ip = p.get("host_ip")

            # Explicitly bound to 0.0.0.0 suggests external exposure
            if host_ip == "0.0.0.0":
                return "LoadBalancer"

            # High port numbers suggest NodePort
            if host_port and host_port >= 30000:
                return "NodePort"

            # If host_port != container_port, likely want external exposure
            if host_port and host_port != p["container_port"]:
                return "ClusterIP"

        return "ClusterIP"

    def _port_name(self, port: int, protocol: str, idx: int) -> str:
        """Generate a name for a service port."""
        well_known = {
            80: "http",
            443: "https",
            3000: "http-app",
            3306: "mysql",
            5432: "postgres",
            6379: "redis",
            8080: "http-alt",
            8443: "https-alt",
            9090: "prometheus",
            27017: "mongodb",
            5672: "amqp",
            15672: "rabbitmq-mgmt",
            9200: "elasticsearch",
            9300: "es-transport",
        }

        name = well_known.get(port, f"{protocol.lower()}-{port}")
        if idx > 0 and name in well_known.values():
            name = f"{name}-{idx}"
        return name
