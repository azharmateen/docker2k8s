# docker2k8s

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-blue?logo=anthropic&logoColor=white)](https://claude.ai/code)


Convert `docker-compose.yml` to production-ready Kubernetes manifests in one command.

```bash
pip install docker2k8s
docker2k8s convert docker-compose.yml -o k8s/ --namespace myapp --provider eks
```

## Why docker2k8s?

Moving from Docker Compose to Kubernetes shouldn't require a PhD. `docker2k8s` reads your existing `docker-compose.yml` and generates real, deployable Kubernetes manifests with best practices baked in.

## Features

- **Full Compose Support** - Services, volumes, networks, ports, environment, depends_on, healthchecks
- **7 Resource Types** - Deployment, Service, ConfigMap, Secret, PersistentVolumeClaim, Ingress, HPA
- **Cloud Provider Presets** - EKS, GKE, AKS, k3s with correct storage classes, annotations, and ingress controllers
- **Smart Defaults** - Resource limits, health probes, security contexts, scaling policies
- **Secret Detection** - Variables with `password`, `secret`, `key`, `token` auto-route to Kubernetes Secrets
- **Validation** - Checks for port conflicts, missing fields, DNS name compliance, selector mismatches
- **Dry Run** - Preview all manifests in terminal before writing files

## Quickstart

```bash
# Install
pip install docker2k8s

# Convert with defaults
docker2k8s convert docker-compose.yml -o k8s/

# Target a specific cloud provider
docker2k8s convert docker-compose.yml -o k8s/ --namespace production --provider eks

# Preview without writing files
docker2k8s convert docker-compose.yml --dry-run

# Inspect what would be generated
docker2k8s inspect docker-compose.yml
```

## What Gets Generated

Given a `docker-compose.yml` with a web app and database:

```
k8s/
  namespace.yaml
  web-deployment.yaml
  web-service.yaml
  web-configmap.yaml
  web-secret.yaml
  web-ingress.yaml
  web-hpa.yaml
  db-deployment.yaml
  db-service.yaml
  db-configmap.yaml
  db-secret.yaml
  db-data-pvc.yaml
  db-hpa.yaml
```

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `-o, --output` | Output directory | `k8s/` |
| `-n, --namespace` | Kubernetes namespace | `default` |
| `--provider` | Cloud provider (generic/eks/gke/aks/k3s) | `generic` |
| `--dry-run` | Print to stdout only | `false` |
| `--single-file` | All manifests in one file | `false` |
| `--no-hpa` | Skip HPA generation | enabled |
| `--no-ingress` | Skip Ingress generation | enabled |

## Provider Support

| Provider | Storage Class | Ingress | LB Annotations |
|----------|--------------|---------|----------------|
| **generic** | - | nginx | standard |
| **eks** | gp3 | ALB | NLB + cross-zone |
| **gke** | standard-rwo | gce | NEG + external |
| **aks** | managed-premium | nginx | Azure DNS |
| **k3s** | local-path | traefik | - |

## Architecture

```
docker-compose.yml
       |
  [Parser] -- normalize ports, env, volumes, healthchecks
       |
  [Converter] -- split secrets, route to generators
       |
  [Generators] -- Deployment, Service, ConfigMap, Secret, PVC, Ingress, HPA
       |
  [Provider] -- apply cloud-specific annotations and storage classes
       |
  [Validator] -- check required fields, port conflicts, DNS names
       |
   k8s/*.yaml
```

## License

MIT
