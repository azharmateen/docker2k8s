"""Generate Kubernetes Deployment manifests."""

from typing import Any


class DeploymentGenerator:
    """Generate a Deployment manifest from a docker-compose service."""

    def __init__(
        self,
        service_name: str,
        service_config: dict[str, Any],
        namespace: str,
        provider_config: Any,
        has_configmap: bool = False,
        has_secret: bool = False,
    ):
        self.name = service_name
        self.config = service_config
        self.namespace = namespace
        self.provider = provider_config
        self.has_configmap = has_configmap
        self.has_secret = has_secret

    def generate(self) -> dict:
        """Generate the Deployment manifest."""
        replicas = self._get_replicas()
        containers = [self._build_container()]
        volumes = self._build_volumes()

        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": f"{self.name}-deployment",
                "namespace": self.namespace,
                "labels": {
                    "app": self.name,
                    "managed-by": "docker2k8s",
                },
            },
            "spec": {
                "replicas": replicas,
                "selector": {
                    "matchLabels": {
                        "app": self.name,
                    },
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": self.name,
                        },
                    },
                    "spec": {
                        "containers": containers,
                    },
                },
            },
        }

        if volumes:
            deployment["spec"]["template"]["spec"]["volumes"] = volumes

        # Restart policy mapping
        restart = self.config.get("restart", "no")
        if restart == "always" or restart == "unless-stopped":
            deployment["spec"]["template"]["spec"]["restartPolicy"] = "Always"
        elif restart == "on-failure":
            deployment["spec"]["template"]["spec"]["restartPolicy"] = "OnFailure"

        # Security context
        security_context = self._build_pod_security_context()
        if security_context:
            deployment["spec"]["template"]["spec"]["securityContext"] = security_context

        # Provider-specific annotations
        annotations = self.provider.get_deployment_annotations()
        if annotations:
            deployment["metadata"]["annotations"] = annotations

        return deployment

    def _build_container(self) -> dict:
        """Build the container spec."""
        container = {
            "name": self.name,
            "image": self.config.get("image", self.name),
            "resources": self._build_resources(),
        }

        # Ports
        ports = self._build_container_ports()
        if ports:
            container["ports"] = ports

        # Command and args
        command = self.config.get("command")
        if command:
            if isinstance(command, str):
                container["command"] = ["/bin/sh", "-c", command]
            elif isinstance(command, list):
                container["command"] = command

        entrypoint = self.config.get("entrypoint")
        if entrypoint:
            if isinstance(entrypoint, str):
                container["command"] = [entrypoint]
            elif isinstance(entrypoint, list):
                container["command"] = entrypoint

        # Working directory
        if self.config.get("working_dir"):
            container["workingDir"] = self.config["working_dir"]

        # Environment from ConfigMap and Secret
        env_from = []
        if self.has_configmap:
            env_from.append({
                "configMapRef": {"name": f"{self.name}-configmap"},
            })
        if self.has_secret:
            env_from.append({
                "secretRef": {"name": f"{self.name}-secret"},
            })
        if env_from:
            container["envFrom"] = env_from

        # Volume mounts
        volume_mounts = self._build_volume_mounts()
        if volume_mounts:
            container["volumeMounts"] = volume_mounts

        # Health checks
        healthcheck = self.config.get("healthcheck")
        if healthcheck:
            probe = self._build_probe(healthcheck)
            container["livenessProbe"] = probe
            container["readinessProbe"] = self._build_readiness_probe(healthcheck)
        else:
            # Auto-generate TCP probe from first port
            ports_config = self.config.get("ports", [])
            if ports_config:
                first_port = ports_config[0].get("container_port", 80)
                container["readinessProbe"] = {
                    "tcpSocket": {"port": first_port},
                    "initialDelaySeconds": 10,
                    "periodSeconds": 10,
                }
                container["livenessProbe"] = {
                    "tcpSocket": {"port": first_port},
                    "initialDelaySeconds": 30,
                    "periodSeconds": 30,
                }

        # Security context for container
        sec_ctx = self._build_container_security_context()
        if sec_ctx:
            container["securityContext"] = sec_ctx

        return container

    def _build_container_ports(self) -> list[dict]:
        """Build container port specifications."""
        ports = []
        for p in self.config.get("ports", []):
            port_spec = {
                "containerPort": p["container_port"],
                "protocol": p.get("protocol", "tcp").upper(),
            }
            ports.append(port_spec)
        return ports

    def _build_resources(self) -> dict:
        """Build resource requests and limits."""
        deploy = self.config.get("deploy", {})
        resources_config = deploy.get("resources", {})

        if resources_config:
            result = {}
            limits = resources_config.get("limits", {})
            reservations = resources_config.get("reservations", {})

            if limits:
                result["limits"] = {}
                if limits.get("cpus"):
                    result["limits"]["cpu"] = limits["cpus"]
                if limits.get("memory"):
                    result["limits"]["memory"] = self._normalize_memory(limits["memory"])

            if reservations:
                result["requests"] = {}
                if reservations.get("cpus"):
                    result["requests"]["cpu"] = reservations["cpus"]
                if reservations.get("memory"):
                    result["requests"]["memory"] = self._normalize_memory(reservations["memory"])

            return result

        # Default resource limits
        return {
            "requests": {
                "cpu": "100m",
                "memory": "128Mi",
            },
            "limits": {
                "cpu": "500m",
                "memory": "512Mi",
            },
        }

    def _normalize_memory(self, mem: str) -> str:
        """Normalize Docker memory format to Kubernetes format."""
        if isinstance(mem, (int, float)):
            return f"{int(mem)}Mi"
        mem = str(mem).strip()
        # Docker uses 'm' for megabytes, K8s uses 'Mi'
        mem = mem.replace("g", "Gi").replace("m", "Mi").replace("k", "Ki")
        # Fix double suffix
        mem = mem.replace("MiMi", "Mi").replace("GiGi", "Gi").replace("KiKi", "Ki")
        return mem

    def _build_probe(self, healthcheck: dict) -> dict:
        """Build a liveness probe from a compose healthcheck."""
        test = healthcheck.get("test", "")

        probe = {
            "initialDelaySeconds": healthcheck.get("start_period", 15),
            "periodSeconds": healthcheck.get("interval", 30),
            "timeoutSeconds": healthcheck.get("timeout", 10),
            "failureThreshold": healthcheck.get("retries", 3),
        }

        # Parse the test command to determine probe type
        if "curl" in test or "wget" in test:
            # Try to extract URL for HTTP probe
            import re
            url_match = re.search(r"https?://[^\s]+", test)
            if url_match:
                url = url_match.group()
                # Extract path
                path = "/"
                if "localhost" in url or "127.0.0.1" in url:
                    parts = url.split("/", 3)
                    if len(parts) > 3:
                        path = "/" + parts[3]
                port_match = re.search(r":(\d+)", url)
                port = int(port_match.group(1)) if port_match else 80

                probe["httpGet"] = {"path": path, "port": port}
                return probe

        # Default to exec probe
        probe["exec"] = {"command": ["/bin/sh", "-c", test]}
        return probe

    def _build_readiness_probe(self, healthcheck: dict) -> dict:
        """Build a readiness probe (slightly faster than liveness)."""
        probe = self._build_probe(healthcheck)
        probe["initialDelaySeconds"] = max(5, probe.get("initialDelaySeconds", 15) // 2)
        probe["periodSeconds"] = max(5, probe.get("periodSeconds", 30) // 2)
        return probe

    def _build_volume_mounts(self) -> list[dict]:
        """Build volume mounts for the container."""
        mounts = []
        for vol in self.config.get("volumes", []):
            source = vol.get("source", "")
            target = vol.get("target", "")
            if not target:
                continue

            mount = {
                "name": self._volume_name(source, target),
                "mountPath": target,
            }
            if vol.get("read_only"):
                mount["readOnly"] = True
            mounts.append(mount)

        # tmpfs mounts
        for idx, tmpfs in enumerate(self.config.get("tmpfs", [])):
            path = tmpfs if isinstance(tmpfs, str) else tmpfs.get("target", f"/tmp/tmpfs-{idx}")
            mounts.append({
                "name": f"tmpfs-{idx}",
                "mountPath": path,
            })

        return mounts

    def _build_volumes(self) -> list[dict]:
        """Build pod-level volume definitions."""
        volumes = []
        for vol in self.config.get("volumes", []):
            source = vol.get("source", "")
            target = vol.get("target", "")
            if not target:
                continue

            vol_name = self._volume_name(source, target)

            if vol["type"] == "bind":
                volumes.append({
                    "name": vol_name,
                    "hostPath": {
                        "path": source,
                        "type": "DirectoryOrCreate",
                    },
                })
            elif vol["type"] == "volume":
                pvc_name = f"{self.name}-{source}-pvc" if source else vol_name
                volumes.append({
                    "name": vol_name,
                    "persistentVolumeClaim": {
                        "claimName": pvc_name,
                    },
                })
            else:
                volumes.append({
                    "name": vol_name,
                    "emptyDir": {},
                })

        # tmpfs volumes
        for idx, _ in enumerate(self.config.get("tmpfs", [])):
            volumes.append({
                "name": f"tmpfs-{idx}",
                "emptyDir": {
                    "medium": "Memory",
                },
            })

        return volumes

    def _volume_name(self, source: str, target: str) -> str:
        """Generate a safe volume name."""
        base = source or target
        # Clean up the name: replace non-alphanumeric with dashes
        import re
        name = re.sub(r"[^a-zA-Z0-9]", "-", base).strip("-").lower()
        name = re.sub(r"-+", "-", name)
        return name[:63] if name else "data"

    def _build_pod_security_context(self) -> dict:
        """Build pod-level security context."""
        ctx = {}
        user = self.config.get("user")
        if user:
            parts = str(user).split(":")
            try:
                ctx["runAsUser"] = int(parts[0])
                if len(parts) > 1:
                    ctx["runAsGroup"] = int(parts[1])
            except ValueError:
                pass
        return ctx

    def _build_container_security_context(self) -> dict:
        """Build container-level security context."""
        ctx = {}
        if self.config.get("privileged"):
            ctx["privileged"] = True
        if self.config.get("read_only"):
            ctx["readOnlyRootFilesystem"] = True

        cap_add = self.config.get("cap_add", [])
        cap_drop = self.config.get("cap_drop", [])
        if cap_add or cap_drop:
            ctx["capabilities"] = {}
            if cap_add:
                ctx["capabilities"]["add"] = cap_add
            if cap_drop:
                ctx["capabilities"]["drop"] = cap_drop

        return ctx

    def _get_replicas(self) -> int:
        """Get replica count from deploy config."""
        deploy = self.config.get("deploy", {})
        return deploy.get("replicas", 1)
