"""Provider-specific configurations for different Kubernetes platforms."""


class ProviderConfig:
    """Cloud provider-specific configuration for generated manifests."""

    PROVIDERS = {
        "generic": {
            "storage_class": None,
            "ingress_class": "nginx",
            "deployment_annotations": {},
            "service_annotations": {},
            "ingress_annotations": {
                "nginx.ingress.kubernetes.io/proxy-body-size": "50m",
                "nginx.ingress.kubernetes.io/proxy-read-timeout": "60",
            },
        },
        "eks": {
            "storage_class": "gp3",
            "ingress_class": "alb",
            "deployment_annotations": {
                "cluster-autoscaler.kubernetes.io/safe-to-evict": "true",
            },
            "service_annotations": {},
            "service_lb_annotations": {
                "service.beta.kubernetes.io/aws-load-balancer-type": "nlb",
                "service.beta.kubernetes.io/aws-load-balancer-scheme": "internet-facing",
                "service.beta.kubernetes.io/aws-load-balancer-cross-zone-load-balancing-enabled": "true",
            },
            "ingress_annotations": {
                "alb.ingress.kubernetes.io/scheme": "internet-facing",
                "alb.ingress.kubernetes.io/target-type": "ip",
                "alb.ingress.kubernetes.io/healthcheck-path": "/",
                "alb.ingress.kubernetes.io/listen-ports": '[{"HTTP": 80}, {"HTTPS": 443}]',
            },
        },
        "gke": {
            "storage_class": "standard-rwo",
            "ingress_class": "gce",
            "deployment_annotations": {
                "autopilot.gke.io/resource-adjustment": "true",
            },
            "service_annotations": {},
            "service_lb_annotations": {
                "cloud.google.com/load-balancer-type": "External",
                "cloud.google.com/neg": '{"ingress": true}',
            },
            "ingress_annotations": {
                "kubernetes.io/ingress.class": "gce",
                "kubernetes.io/ingress.global-static-ip-name": "",
                "networking.gke.io/managed-certificates": "",
            },
        },
        "aks": {
            "storage_class": "managed-premium",
            "ingress_class": "nginx",
            "deployment_annotations": {},
            "service_annotations": {},
            "service_lb_annotations": {
                "service.beta.kubernetes.io/azure-load-balancer-internal": "false",
                "service.beta.kubernetes.io/azure-dns-label-name": "",
            },
            "ingress_annotations": {
                "nginx.ingress.kubernetes.io/proxy-body-size": "50m",
                "nginx.ingress.kubernetes.io/ssl-redirect": "true",
                "nginx.ingress.kubernetes.io/use-regex": "true",
            },
        },
        "k3s": {
            "storage_class": "local-path",
            "ingress_class": "traefik",
            "deployment_annotations": {},
            "service_annotations": {},
            "ingress_annotations": {
                "traefik.ingress.kubernetes.io/router.entrypoints": "web,websecure",
                "traefik.ingress.kubernetes.io/router.middlewares": "",
            },
        },
    }

    def __init__(self, provider: str = "generic"):
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Supported: {list(self.PROVIDERS.keys())}")
        self.provider = provider
        self.config = self.PROVIDERS[provider]

    def get_storage_class(self) -> str | None:
        """Get the storage class for PVCs."""
        return self.config.get("storage_class")

    def get_ingress_class(self) -> str:
        """Get the ingress class name."""
        return self.config.get("ingress_class", "nginx")

    def get_deployment_annotations(self) -> dict:
        """Get provider-specific deployment annotations."""
        return self.config.get("deployment_annotations", {})

    def get_service_annotations(self, service_type: str = "ClusterIP") -> dict:
        """Get provider-specific service annotations."""
        annotations = dict(self.config.get("service_annotations", {}))
        if service_type == "LoadBalancer":
            annotations.update(self.config.get("service_lb_annotations", {}))
        return annotations

    def get_ingress_annotations(self) -> dict:
        """Get provider-specific ingress annotations."""
        return dict(self.config.get("ingress_annotations", {}))
