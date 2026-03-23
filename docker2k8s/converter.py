"""Main converter: orchestrates generation of all Kubernetes manifests from compose data."""

from typing import Any

from docker2k8s.generators.configmap import ConfigMapGenerator
from docker2k8s.generators.deployment import DeploymentGenerator
from docker2k8s.generators.hpa import HPAGenerator
from docker2k8s.generators.ingress import IngressGenerator
from docker2k8s.generators.service import ServiceGenerator
from docker2k8s.providers import ProviderConfig


class Converter:
    """Convert parsed docker-compose data to Kubernetes manifests."""

    def __init__(
        self,
        compose_data: dict[str, Any],
        namespace: str = "default",
        provider: str = "generic",
        enable_hpa: bool = True,
        enable_ingress: bool = True,
    ):
        self.compose_data = compose_data
        self.namespace = namespace
        self.provider_config = ProviderConfig(provider)
        self.enable_hpa = enable_hpa
        self.enable_ingress = enable_ingress

    def convert(self) -> dict[str, Any]:
        """Convert all services to Kubernetes manifests.

        Returns a dict of {filename: manifest_dict}.
        """
        manifests = {}
        services = self.compose_data.get("services", {})

        # Generate namespace manifest if not default
        if self.namespace != "default":
            manifests["namespace"] = self._generate_namespace()

        for name, svc in services.items():
            # Generate PVCs for named volumes
            pvc_manifests = self._generate_pvcs(name, svc)
            manifests.update(pvc_manifests)

            # ConfigMap for environment variables
            env_vars = svc.get("environment", {})
            secrets, config_vars = self._split_secrets(env_vars)

            if config_vars:
                gen = ConfigMapGenerator(name, config_vars, self.namespace)
                manifests[f"{name}-configmap"] = gen.generate()

            if secrets:
                manifests[f"{name}-secret"] = self._generate_secret(name, secrets)

            # Deployment
            dep_gen = DeploymentGenerator(
                service_name=name,
                service_config=svc,
                namespace=self.namespace,
                provider_config=self.provider_config,
                has_configmap=bool(config_vars),
                has_secret=bool(secrets),
            )
            manifests[f"{name}-deployment"] = dep_gen.generate()

            # Service
            if svc.get("ports"):
                svc_gen = ServiceGenerator(
                    service_name=name,
                    service_config=svc,
                    namespace=self.namespace,
                    provider_config=self.provider_config,
                )
                manifests[f"{name}-service"] = svc_gen.generate()

                # Ingress for externally-exposed ports
                if self.enable_ingress and self._has_external_ports(svc):
                    ing_gen = IngressGenerator(
                        service_name=name,
                        service_config=svc,
                        namespace=self.namespace,
                        provider_config=self.provider_config,
                    )
                    manifests[f"{name}-ingress"] = ing_gen.generate()

            # HPA
            if self.enable_hpa:
                hpa_gen = HPAGenerator(
                    service_name=name,
                    service_config=svc,
                    namespace=self.namespace,
                )
                manifests[f"{name}-hpa"] = hpa_gen.generate()

        return manifests

    def _generate_namespace(self) -> dict:
        """Generate a Namespace manifest."""
        return {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": self.namespace,
                "labels": {
                    "name": self.namespace,
                    "managed-by": "docker2k8s",
                },
            },
        }

    def _generate_pvcs(self, service_name: str, svc: dict) -> dict[str, Any]:
        """Generate PersistentVolumeClaim manifests for named volumes."""
        pvcs = {}
        top_volumes = self.compose_data.get("volumes", {})

        for vol in svc.get("volumes", []):
            source = vol.get("source", "")
            if vol["type"] == "volume" and source and source in top_volumes:
                pvc_name = f"{service_name}-{source}-pvc"
                storage_class = self.provider_config.get_storage_class()

                pvc = {
                    "apiVersion": "v1",
                    "kind": "PersistentVolumeClaim",
                    "metadata": {
                        "name": pvc_name,
                        "namespace": self.namespace,
                        "labels": {
                            "app": service_name,
                            "managed-by": "docker2k8s",
                        },
                    },
                    "spec": {
                        "accessModes": ["ReadWriteOnce"],
                        "resources": {
                            "requests": {
                                "storage": "1Gi",
                            },
                        },
                    },
                }

                if storage_class:
                    pvc["spec"]["storageClassName"] = storage_class

                pvcs[pvc_name] = pvc

        return pvcs

    def _generate_secret(self, service_name: str, secrets: dict[str, str]) -> dict:
        """Generate a Secret manifest for sensitive environment variables."""
        import base64

        encoded_data = {}
        for key, value in secrets.items():
            encoded_data[key] = base64.b64encode(value.encode()).decode()

        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": f"{service_name}-secret",
                "namespace": self.namespace,
                "labels": {
                    "app": service_name,
                    "managed-by": "docker2k8s",
                },
            },
            "type": "Opaque",
            "data": encoded_data,
        }

    def _split_secrets(self, env_vars: dict[str, str]) -> tuple[dict, dict]:
        """Split environment variables into secrets and config vars.

        Variables containing 'password', 'secret', 'key', 'token', 'credential'
        in the name are treated as secrets.
        """
        secret_patterns = ("password", "secret", "key", "token", "credential", "api_key", "apikey")
        secrets = {}
        config = {}

        for k, v in env_vars.items():
            k_lower = k.lower()
            if any(pat in k_lower for pat in secret_patterns):
                secrets[k] = v
            else:
                config[k] = v

        return secrets, config

    def _has_external_ports(self, svc: dict) -> bool:
        """Check if a service has externally-exposed ports (host_port defined)."""
        for port in svc.get("ports", []):
            if port.get("host_port"):
                return True
        return False
