"""Parse docker-compose.yml files into a normalized data structure."""

import os
import re
from typing import Any

import yaml


class ComposeParser:
    """Parse and normalize docker-compose.yml files."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.base_dir = os.path.dirname(os.path.abspath(filepath))

    def parse(self) -> dict[str, Any]:
        """Parse the compose file and return normalized data."""
        with open(self.filepath, "r") as f:
            raw = yaml.safe_load(f)

        if raw is None:
            raise ValueError(f"Empty or invalid compose file: {self.filepath}")

        # Detect compose file version
        version = raw.get("version", "3")

        # Normalize services
        services = {}
        raw_services = raw.get("services", raw if "version" not in raw else {})

        for name, svc in raw_services.items():
            if name in ("version", "volumes", "networks", "configs", "secrets"):
                continue
            services[name] = self._normalize_service(name, svc)

        # Normalize top-level volumes
        volumes = self._normalize_volumes(raw.get("volumes", {}))

        # Normalize top-level networks
        networks = self._normalize_networks(raw.get("networks", {}))

        return {
            "version": version,
            "services": services,
            "volumes": volumes,
            "networks": networks,
        }

    def _normalize_service(self, name: str, svc: dict) -> dict:
        """Normalize a single service definition."""
        normalized = {
            "name": name,
            "image": svc.get("image", ""),
            "build": self._normalize_build(svc.get("build")),
            "ports": self._normalize_ports(svc.get("ports", [])),
            "environment": self._normalize_environment(svc.get("environment")),
            "env_file": svc.get("env_file", []),
            "volumes": self._normalize_volumes_mounts(svc.get("volumes", [])),
            "depends_on": self._normalize_depends_on(svc.get("depends_on")),
            "networks": svc.get("networks", []),
            "command": svc.get("command"),
            "entrypoint": svc.get("entrypoint"),
            "restart": svc.get("restart", "no"),
            "healthcheck": self._normalize_healthcheck(svc.get("healthcheck")),
            "deploy": svc.get("deploy", {}),
            "labels": svc.get("labels", {}),
            "working_dir": svc.get("working_dir"),
            "user": svc.get("user"),
            "cap_add": svc.get("cap_add", []),
            "cap_drop": svc.get("cap_drop", []),
            "privileged": svc.get("privileged", False),
            "read_only": svc.get("read_only", False),
            "tmpfs": svc.get("tmpfs", []),
            "logging": svc.get("logging", {}),
        }

        # If no image is specified but build is, use the service name as image
        if not normalized["image"] and normalized["build"]:
            normalized["image"] = name

        return normalized

    def _normalize_build(self, build) -> dict | None:
        """Normalize build configuration."""
        if build is None:
            return None
        if isinstance(build, str):
            return {"context": build, "dockerfile": "Dockerfile"}
        return {
            "context": build.get("context", "."),
            "dockerfile": build.get("dockerfile", "Dockerfile"),
            "args": build.get("args", {}),
        }

    def _normalize_ports(self, ports: list) -> list[dict]:
        """Normalize port mappings to structured format.

        Supports:
          - "8080:80"
          - "8080:80/tcp"
          - "127.0.0.1:8080:80"
          - {"target": 80, "published": 8080, "protocol": "tcp"}
        """
        normalized = []
        for port in ports:
            if isinstance(port, dict):
                normalized.append({
                    "host_port": port.get("published"),
                    "container_port": port["target"],
                    "protocol": port.get("protocol", "tcp"),
                    "host_ip": port.get("host_ip"),
                })
            elif isinstance(port, (str, int)):
                parsed = self._parse_port_string(str(port))
                normalized.append(parsed)
        return normalized

    def _parse_port_string(self, port_str: str) -> dict:
        """Parse a port string like '8080:80/tcp' or '127.0.0.1:8080:80'."""
        protocol = "tcp"
        if "/" in port_str:
            port_str, protocol = port_str.rsplit("/", 1)

        parts = port_str.split(":")
        if len(parts) == 3:
            # host_ip:host_port:container_port
            return {
                "host_ip": parts[0],
                "host_port": int(parts[1]),
                "container_port": int(parts[2]),
                "protocol": protocol,
            }
        elif len(parts) == 2:
            # host_port:container_port
            return {
                "host_ip": None,
                "host_port": int(parts[0]),
                "container_port": int(parts[1]),
                "protocol": protocol,
            }
        else:
            # container_port only
            return {
                "host_ip": None,
                "host_port": None,
                "container_port": int(parts[0]),
                "protocol": protocol,
            }

    def _normalize_environment(self, env) -> dict[str, str]:
        """Normalize environment variables from list or dict format."""
        if env is None:
            return {}
        if isinstance(env, dict):
            return {k: str(v) if v is not None else "" for k, v in env.items()}
        if isinstance(env, list):
            result = {}
            for item in env:
                if "=" in item:
                    key, value = item.split("=", 1)
                    result[key] = value
                else:
                    result[item] = ""
            return result
        return {}

    def _normalize_volumes_mounts(self, volumes: list) -> list[dict]:
        """Normalize volume mounts."""
        normalized = []
        for vol in volumes:
            if isinstance(vol, dict):
                normalized.append({
                    "source": vol.get("source", ""),
                    "target": vol["target"],
                    "type": vol.get("type", "volume"),
                    "read_only": vol.get("read_only", False),
                })
            elif isinstance(vol, str):
                parts = vol.split(":")
                if len(parts) >= 2:
                    source = parts[0]
                    target = parts[1]
                    read_only = len(parts) > 2 and parts[2] == "ro"
                    # Determine type: paths starting with . or / are bind mounts
                    vol_type = "bind" if source.startswith((".","/" )) else "volume"
                    normalized.append({
                        "source": source,
                        "target": target,
                        "type": vol_type,
                        "read_only": read_only,
                    })
                else:
                    # Anonymous volume
                    normalized.append({
                        "source": "",
                        "target": parts[0],
                        "type": "volume",
                        "read_only": False,
                    })
        return normalized

    def _normalize_depends_on(self, depends_on) -> list[dict]:
        """Normalize depends_on to structured format."""
        if depends_on is None:
            return []
        if isinstance(depends_on, list):
            return [{"service": s, "condition": "service_started"} for s in depends_on]
        if isinstance(depends_on, dict):
            return [
                {"service": name, "condition": cfg.get("condition", "service_started")}
                for name, cfg in depends_on.items()
            ]
        return []

    def _normalize_healthcheck(self, hc) -> dict | None:
        """Normalize healthcheck configuration."""
        if hc is None:
            return None
        if hc.get("disable"):
            return None

        test = hc.get("test", [])
        if isinstance(test, str):
            test_cmd = test
        elif isinstance(test, list):
            # Remove CMD or CMD-SHELL prefix
            if test and test[0] in ("CMD", "CMD-SHELL"):
                test_cmd = " ".join(test[1:])
            else:
                test_cmd = " ".join(test)
        else:
            test_cmd = ""

        return {
            "test": test_cmd,
            "interval": self._parse_duration(hc.get("interval", "30s")),
            "timeout": self._parse_duration(hc.get("timeout", "10s")),
            "retries": hc.get("retries", 3),
            "start_period": self._parse_duration(hc.get("start_period", "0s")),
        }

    def _parse_duration(self, duration) -> int:
        """Parse a duration string (e.g., '30s', '1m', '5m30s') to seconds."""
        if isinstance(duration, (int, float)):
            return int(duration)
        if not isinstance(duration, str):
            return 30

        total = 0
        matches = re.findall(r"(\d+)(h|m|s|ms|us)", duration)
        if not matches:
            try:
                return int(duration)
            except ValueError:
                return 30

        for value, unit in matches:
            v = int(value)
            if unit == "h":
                total += v * 3600
            elif unit == "m":
                total += v * 60
            elif unit == "s":
                total += v
            elif unit == "ms":
                total += max(1, v // 1000)
        return total or 30

    def _normalize_volumes(self, volumes) -> dict:
        """Normalize top-level volumes."""
        if volumes is None:
            return {}
        result = {}
        for name, config in volumes.items():
            if config is None:
                result[name] = {"driver": "local"}
            else:
                result[name] = {
                    "driver": config.get("driver", "local"),
                    "driver_opts": config.get("driver_opts", {}),
                    "labels": config.get("labels", {}),
                    "external": config.get("external", False),
                }
        return result

    def _normalize_networks(self, networks) -> dict:
        """Normalize top-level networks."""
        if networks is None:
            return {}
        result = {}
        for name, config in networks.items():
            if config is None:
                result[name] = {"driver": "bridge"}
            else:
                result[name] = {
                    "driver": config.get("driver", "bridge"),
                    "external": config.get("external", False),
                }
        return result
