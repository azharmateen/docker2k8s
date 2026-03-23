"""CLI entry point for docker2k8s."""

import os
import sys

import click
import yaml
from rich.console import Console
from rich.table import Table

from docker2k8s.converter import Converter
from docker2k8s.parser import ComposeParser
from docker2k8s.validator import ManifestValidator

console = Console()


@click.group()
@click.version_option(package_name="docker2k8s")
def main():
    """Convert docker-compose.yml to production-ready Kubernetes manifests."""
    pass


@main.command()
@click.argument("compose_file", type=click.Path(exists=True))
@click.option("-o", "--output", default="k8s/", help="Output directory for manifests")
@click.option("-n", "--namespace", default="default", help="Kubernetes namespace")
@click.option(
    "--provider",
    type=click.Choice(["generic", "eks", "gke", "aks", "k3s"]),
    default="generic",
    help="Cloud provider for specific annotations/storage classes",
)
@click.option("--dry-run", is_flag=True, help="Print manifests to stdout without writing files")
@click.option("--single-file", is_flag=True, help="Output all manifests in a single file")
@click.option("--hpa/--no-hpa", default=True, help="Generate HorizontalPodAutoscaler resources")
@click.option("--ingress/--no-ingress", default=True, help="Generate Ingress resources for exposed ports")
def convert(compose_file, output, namespace, provider, dry_run, single_file, hpa, ingress):
    """Convert a docker-compose.yml file to Kubernetes manifests.

    Example:
        docker2k8s convert docker-compose.yml -o k8s/ --namespace myapp --provider eks
    """
    console.print(f"[bold blue]Parsing[/] {compose_file}...")

    try:
        parser = ComposeParser(compose_file)
        compose_data = parser.parse()
    except Exception as e:
        console.print(f"[bold red]Error parsing compose file:[/] {e}")
        sys.exit(1)

    service_count = len(compose_data.get("services", {}))
    console.print(f"[green]Found {service_count} services[/]")

    converter = Converter(
        compose_data=compose_data,
        namespace=namespace,
        provider=provider,
        enable_hpa=hpa,
        enable_ingress=ingress,
    )

    manifests = converter.convert()

    # Validate
    validator = ManifestValidator()
    errors = validator.validate_all(manifests)
    if errors:
        console.print("[bold yellow]Validation warnings:[/]")
        for err in errors:
            console.print(f"  [yellow]- {err}[/]")

    if dry_run:
        for name, content in manifests.items():
            console.print(f"\n[bold cyan]--- {name} ---[/]")
            console.print(yaml.dump(content, default_flow_style=False))
        return

    os.makedirs(output, exist_ok=True)

    if single_file:
        all_docs = []
        for content in manifests.values():
            all_docs.append(yaml.dump(content, default_flow_style=False))
        combined = "---\n".join(all_docs)
        filepath = os.path.join(output, "all-manifests.yaml")
        with open(filepath, "w") as f:
            f.write(combined)
        console.print(f"[green]Wrote all manifests to {filepath}[/]")
    else:
        for name, content in manifests.items():
            filepath = os.path.join(output, f"{name}.yaml")
            with open(filepath, "w") as f:
                yaml.dump(content, f, default_flow_style=False)
            console.print(f"[green]Wrote[/] {filepath}")

    console.print(f"\n[bold green]Generated {len(manifests)} manifests in {output}[/]")

    # Summary table
    _print_summary(manifests, namespace, provider)


def _print_summary(manifests, namespace, provider):
    """Print a summary table of generated resources."""
    table = Table(title="Generated Kubernetes Resources")
    table.add_column("Resource", style="cyan")
    table.add_column("Kind", style="green")
    table.add_column("Name", style="white")

    for filename, content in manifests.items():
        kind = content.get("kind", "Unknown")
        name = content.get("metadata", {}).get("name", "unknown")
        table.add_row(f"{filename}.yaml", kind, name)

    console.print(table)
    console.print(f"\n[dim]Namespace: {namespace} | Provider: {provider}[/]")


@main.command()
@click.argument("compose_file", type=click.Path(exists=True))
def inspect(compose_file):
    """Inspect a docker-compose.yml and show what would be generated."""
    parser = ComposeParser(compose_file)
    compose_data = parser.parse()

    table = Table(title=f"Services in {compose_file}")
    table.add_column("Service", style="cyan")
    table.add_column("Image", style="green")
    table.add_column("Ports", style="yellow")
    table.add_column("Volumes", style="magenta")
    table.add_column("Depends On", style="blue")

    for name, svc in compose_data.get("services", {}).items():
        image = svc.get("image", svc.get("build", "build-context"))
        # Format ports: "host_port:container_port/protocol"
        port_strs = []
        for p in svc.get("ports", []):
            if isinstance(p, dict):
                hp = p.get("host_port")
                cp = p.get("container_port")
                proto = p.get("protocol", "tcp")
                port_strs.append(f"{hp}:{cp}/{proto}" if hp else f"{cp}/{proto}")
            else:
                port_strs.append(str(p))
        ports = ", ".join(port_strs)
        # Format volumes: "source:target"
        vol_strs = []
        for v in svc.get("volumes", []):
            if isinstance(v, dict):
                src = v.get("source", "")
                tgt = v.get("target", "")
                vol_strs.append(f"{src}:{tgt}" if src else tgt)
            else:
                vol_strs.append(str(v))
        volumes = ", ".join(vol_strs)
        # Format depends_on: normalized to list of dicts with "service" key
        deps = svc.get("depends_on", [])
        if isinstance(deps, list):
            depends = ", ".join(
                d["service"] if isinstance(d, dict) else str(d) for d in deps
            )
        elif isinstance(deps, dict):
            depends = ", ".join(deps.keys())
        else:
            depends = ""
        table.add_row(name, str(image), ports or "-", volumes or "-", depends or "-")

    console.print(table)

    resources = []
    for name in compose_data.get("services", {}):
        resources.extend([
            f"{name}-deployment (Deployment)",
            f"{name}-service (Service)",
            f"{name}-configmap (ConfigMap)",
        ])
    console.print(f"\n[bold]Would generate {len(resources)} resources:[/]")
    for r in resources:
        console.print(f"  [dim]- {r}[/]")


if __name__ == "__main__":
    main()
