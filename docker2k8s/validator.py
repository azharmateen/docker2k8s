"""Validate generated Kubernetes manifests for correctness."""

from typing import Any


class ManifestValidator:
    """Validate Kubernetes manifests for common issues."""

    REQUIRED_FIELDS = {
        "Deployment": ["apiVersion", "kind", "metadata", "spec"],
        "Service": ["apiVersion", "kind", "metadata", "spec"],
        "ConfigMap": ["apiVersion", "kind", "metadata", "data"],
        "Secret": ["apiVersion", "kind", "metadata", "data"],
        "Ingress": ["apiVersion", "kind", "metadata", "spec"],
        "HorizontalPodAutoscaler": ["apiVersion", "kind", "metadata", "spec"],
        "PersistentVolumeClaim": ["apiVersion", "kind", "metadata", "spec"],
        "Namespace": ["apiVersion", "kind", "metadata"],
    }

    def validate_all(self, manifests: dict[str, Any]) -> list[str]:
        """Validate all manifests and return a list of warning messages."""
        errors = []
        seen_ports = {}

        for name, manifest in manifests.items():
            errors.extend(self._validate_required_fields(name, manifest))
            errors.extend(self._validate_metadata(name, manifest))

            kind = manifest.get("kind", "")
            if kind == "Deployment":
                errors.extend(self._validate_deployment(name, manifest))
            elif kind == "Service":
                errors.extend(self._validate_service(name, manifest, seen_ports))
            elif kind == "Ingress":
                errors.extend(self._validate_ingress(name, manifest))
            elif kind == "HorizontalPodAutoscaler":
                errors.extend(self._validate_hpa(name, manifest))

        return errors

    def _validate_required_fields(self, name: str, manifest: dict) -> list[str]:
        """Check that required fields exist."""
        errors = []
        kind = manifest.get("kind", "Unknown")
        required = self.REQUIRED_FIELDS.get(kind, ["apiVersion", "kind", "metadata"])

        for field in required:
            if field not in manifest:
                errors.append(f"[{name}] Missing required field: {field}")

        return errors

    def _validate_metadata(self, name: str, manifest: dict) -> list[str]:
        """Validate metadata section."""
        errors = []
        metadata = manifest.get("metadata", {})

        if not metadata.get("name"):
            errors.append(f"[{name}] Missing metadata.name")

        # Check name format (must be DNS-compatible)
        res_name = metadata.get("name", "")
        if res_name:
            import re
            if not re.match(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$", res_name) and len(res_name) > 1:
                errors.append(f"[{name}] Name '{res_name}' may not be DNS-compatible")
            if len(res_name) > 253:
                errors.append(f"[{name}] Name exceeds 253 character limit")

        return errors

    def _validate_deployment(self, name: str, manifest: dict) -> list[str]:
        """Validate Deployment-specific fields."""
        errors = []
        spec = manifest.get("spec", {})

        # Check replicas
        replicas = spec.get("replicas", 1)
        if replicas < 1:
            errors.append(f"[{name}] Replicas must be >= 1, got {replicas}")

        # Check selector matches template labels
        selector = spec.get("selector", {}).get("matchLabels", {})
        template_labels = spec.get("template", {}).get("metadata", {}).get("labels", {})
        if selector and template_labels:
            for key, value in selector.items():
                if template_labels.get(key) != value:
                    errors.append(f"[{name}] Selector label '{key}={value}' doesn't match template labels")

        # Check containers
        containers = spec.get("template", {}).get("spec", {}).get("containers", [])
        if not containers:
            errors.append(f"[{name}] No containers defined")

        for container in containers:
            if not container.get("image"):
                errors.append(f"[{name}] Container '{container.get('name', '?')}' missing image")

            # Warn about missing resource limits
            resources = container.get("resources", {})
            if not resources.get("limits"):
                errors.append(f"[{name}] Container '{container.get('name', '?')}' missing resource limits")

        return errors

    def _validate_service(self, name: str, manifest: dict, seen_ports: dict) -> list[str]:
        """Validate Service-specific fields."""
        errors = []
        spec = manifest.get("spec", {})

        # Check for valid service type
        svc_type = spec.get("type", "ClusterIP")
        valid_types = ("ClusterIP", "NodePort", "LoadBalancer", "ExternalName")
        if svc_type not in valid_types:
            errors.append(f"[{name}] Invalid service type: {svc_type}")

        # Check ports
        ports = spec.get("ports", [])
        if not ports:
            errors.append(f"[{name}] No ports defined for Service")

        for port in ports:
            port_num = port.get("port")
            if port_num and port_num in seen_ports:
                errors.append(
                    f"[{name}] Port {port_num} conflicts with {seen_ports[port_num]}"
                )
            if port_num:
                seen_ports[port_num] = name

            # NodePort range check
            if svc_type == "NodePort":
                node_port = port.get("nodePort")
                if node_port and (node_port < 30000 or node_port > 32767):
                    errors.append(f"[{name}] NodePort {node_port} out of range (30000-32767)")

        return errors

    def _validate_ingress(self, name: str, manifest: dict) -> list[str]:
        """Validate Ingress-specific fields."""
        errors = []
        spec = manifest.get("spec", {})

        rules = spec.get("rules", [])
        if not rules:
            errors.append(f"[{name}] No rules defined for Ingress")

        for rule in rules:
            paths = rule.get("http", {}).get("paths", [])
            if not paths:
                errors.append(f"[{name}] No paths defined in Ingress rule")

            for path in paths:
                if not path.get("backend", {}).get("service"):
                    errors.append(f"[{name}] Missing backend service in Ingress path")

        return errors

    def _validate_hpa(self, name: str, manifest: dict) -> list[str]:
        """Validate HPA-specific fields."""
        errors = []
        spec = manifest.get("spec", {})

        min_r = spec.get("minReplicas", 1)
        max_r = spec.get("maxReplicas", 1)
        if min_r > max_r:
            errors.append(f"[{name}] minReplicas ({min_r}) > maxReplicas ({max_r})")

        if not spec.get("metrics"):
            errors.append(f"[{name}] No metrics defined for HPA")

        return errors
