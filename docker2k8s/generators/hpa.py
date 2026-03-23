"""Generate Kubernetes HorizontalPodAutoscaler manifests."""

from typing import Any


class HPAGenerator:
    """Generate a HorizontalPodAutoscaler manifest from a docker-compose service."""

    def __init__(
        self,
        service_name: str,
        service_config: dict[str, Any],
        namespace: str,
    ):
        self.name = service_name
        self.config = service_config
        self.namespace = namespace

    def generate(self) -> dict:
        """Generate the HPA manifest."""
        min_replicas, max_replicas = self._get_replica_range()
        metrics = self._build_metrics()

        hpa = {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": f"{self.name}-hpa",
                "namespace": self.namespace,
                "labels": {
                    "app": self.name,
                    "managed-by": "docker2k8s",
                },
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": f"{self.name}-deployment",
                },
                "minReplicas": min_replicas,
                "maxReplicas": max_replicas,
                "metrics": metrics,
            },
        }

        # Add behavior for controlled scaling
        hpa["spec"]["behavior"] = {
            "scaleDown": {
                "stabilizationWindowSeconds": 300,
                "policies": [
                    {
                        "type": "Pods",
                        "value": 1,
                        "periodSeconds": 60,
                    },
                ],
            },
            "scaleUp": {
                "stabilizationWindowSeconds": 60,
                "policies": [
                    {
                        "type": "Pods",
                        "value": 2,
                        "periodSeconds": 60,
                    },
                    {
                        "type": "Percent",
                        "value": 50,
                        "periodSeconds": 60,
                    },
                ],
                "selectPolicy": "Max",
            },
        }

        return hpa

    def _get_replica_range(self) -> tuple[int, int]:
        """Get min/max replicas from deploy config or defaults."""
        deploy = self.config.get("deploy", {})
        replicas = deploy.get("replicas", 1)

        # Check for labels with explicit HPA config
        labels = self.config.get("labels", {})
        if isinstance(labels, dict):
            min_r = labels.get("docker2k8s.hpa.min")
            max_r = labels.get("docker2k8s.hpa.max")
            if min_r and max_r:
                return int(min_r), int(max_r)

        min_replicas = max(1, replicas)
        max_replicas = max(3, replicas * 3)

        return min_replicas, max_replicas

    def _build_metrics(self) -> list[dict]:
        """Build HPA metrics (CPU and memory by default)."""
        labels = self.config.get("labels", {})
        cpu_target = 70
        memory_target = 80

        if isinstance(labels, dict):
            cpu_target = int(labels.get("docker2k8s.hpa.cpu-target", 70))
            memory_target = int(labels.get("docker2k8s.hpa.memory-target", 80))

        return [
            {
                "type": "Resource",
                "resource": {
                    "name": "cpu",
                    "target": {
                        "type": "Utilization",
                        "averageUtilization": cpu_target,
                    },
                },
            },
            {
                "type": "Resource",
                "resource": {
                    "name": "memory",
                    "target": {
                        "type": "Utilization",
                        "averageUtilization": memory_target,
                    },
                },
            },
        ]
