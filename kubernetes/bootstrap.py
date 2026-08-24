#!/usr/bin/env python3
"""kubernetes/bootstrap.py — one-time (idempotent, safe to re-run) setup
for this pilot's kind cluster: creates the cluster, installs Gateway API
CRDs, bootstraps ArgoCD, lets it bring up the rest of the platform
(Traefik/MetalLB/shared Postgres+MariaDB), fixes MetalLB's IP pool for
this specific Docker network, exposes ArgoCD's UI, and applies every
service's ArgoCD Application.

Python, not shell, for the same reason homeserver.py replaced
homeserver.sh and apply-secrets.py replaced apply-secrets.sh (see either
docstring): subprocess.run() with list-form args never goes through a
shell, so this runs identically on Windows/Fedora/Ubuntu/macOS with no
Git-Bash/MSYS path-mangling risk.

Usage: uv run kubernetes/bootstrap.py [--skip-secrets]

Each step below is independently idempotent — re-running this after a
partial failure only redoes what's actually missing, matching the
"already-running lower tier is left untouched" idiom homeserver.py's own
`up core` already has. See kubernetes/README.md's "Cluster" and "What's
installed" sections for what each step actually does and why; this file
is the automated version of the sequence documented there.
"""

from __future__ import annotations

import ipaddress
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

K8S_DIR = Path(__file__).resolve().parent
BASE_DIR = K8S_DIR.parent

sys.path.insert(0, str(K8S_DIR))
from k8s import GREEN, RED, YELLOW, CYAN, BOLD, RESET, info, success, error, warn, header, kubectl_run, kubectl_json, current_context  # noqa: E402

EXPECTED_CONTEXT = "kind-kind-cluster"
ARGOCD_INSTALL_URL = "https://raw.githubusercontent.com/argoproj/argo-cd/v3.4.6/manifests/install.yaml"
GATEWAY_API_CRDS_URL = "https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/standard-install.yaml"

CLUSTER_APPS = [
    "cluster-namespaces",
    "cluster-gateway",
    "cluster-traefik",
    "cluster-metallb",
    "cluster-postgres-shared",
    "cluster-mariadb-shared",
]


def check_prereqs() -> None:
    missing = [tool for tool in ("docker", "kind", "kubectl", "helm") if not shutil.which(tool)]
    if missing:
        error(f"missing on PATH: {', '.join(missing)} — see kubernetes/README.md's Prerequisites section")
        sys.exit(1)
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        error("docker daemon not reachable — is Docker/Docker Desktop actually running?")
        sys.exit(1)
    success("prerequisites present: docker, kind, kubectl, helm")


def create_cluster() -> None:
    existing = subprocess.run(["kind", "get", "clusters"], capture_output=True, text=True, check=True).stdout.split()
    if "kind-cluster" in existing:
        success("kind cluster already exists, skipping create")
        return
    info("creating kind cluster (kubernetes/kind-config.yaml)...")
    subprocess.run(["kind", "create", "cluster", "--config", str(K8S_DIR / "kind-config.yaml")], check=True)
    ctx = current_context()
    if ctx != EXPECTED_CONTEXT:
        warn(f"kubectl context is '{ctx}', expected '{EXPECTED_CONTEXT}' — kind's naming may have changed")
    success("kind cluster created")


def install_gateway_api_crds() -> None:
    existing = kubectl_run(["get", "crd", "gateways.gateway.networking.k8s.io"], check=False)
    if existing.returncode == 0:
        success("Gateway API CRDs already installed, skipping")
        return
    info("installing Gateway API CRDs...")
    kubectl_run(["apply", "-f", GATEWAY_API_CRDS_URL])
    success("Gateway API CRDs installed")


def apply_namespaces() -> None:
    info("applying namespaces (bootstraps 'argocd' before ArgoCD itself can exist)...")
    kubectl_run(["apply", "-f", str(K8S_DIR / "cluster" / "namespaces.yaml")])
    success("namespaces applied")


def bootstrap_argocd() -> None:
    existing = kubectl_run(["-n", "argocd", "get", "deployment", "argocd-server"], check=False)
    if existing.returncode == 0:
        success("ArgoCD already installed, skipping")
        return
    info("installing ArgoCD (server-side apply — its CRDs are too large for client-side apply)...")
    subprocess.run(
        ["kubectl", "apply", "-n", "argocd", "-f", ARGOCD_INSTALL_URL, "--server-side", "--force-conflicts"],
        check=True,
    )
    info("waiting for ArgoCD deployments to become available (this can take a few minutes)...")
    subprocess.run(
        ["kubectl", "-n", "argocd", "wait", "--for=condition=available", "--timeout=300s", "deployment", "--all"],
        check=True,
    )
    success("ArgoCD is up")


def fix_metallb_pool() -> None:
    pool_path = K8S_DIR / "cluster" / "metallb" / "resources" / "ipaddresspool.yaml"
    content = pool_path.read_text(encoding="utf-8")
    if "172.18.255.200-172.18.255.250" not in content:
        success("MetalLB IP pool already customized, skipping")
        return
    try:
        result = subprocess.run(["docker", "network", "inspect", "kind"], capture_output=True, text=True, check=True)
        subnet = json.loads(result.stdout)[0]["IPAM"]["Config"][0]["Subnet"]
    except (subprocess.CalledProcessError, KeyError, IndexError, json.JSONDecodeError):
        warn("could not detect the 'kind' Docker network's subnet — leaving ipaddresspool.yaml as a placeholder, fix it manually (see that file's own comment)")
        return
    network = ipaddress.ip_network(subnet, strict=False)
    first_two_octets = ".".join(str(network.network_address).split(".")[:2])
    new_range = f"{first_two_octets}.255.200-{first_two_octets}.255.250"
    new_content = content.replace("172.18.255.200-172.18.255.250", new_range)
    pool_path.write_text(new_content, encoding="utf-8")
    warn(f"MetalLB IP pool updated to {new_range} (detected from Docker network 'kind': {subnet}) — REVIEW AND COMMIT kubernetes/cluster/metallb/resources/ipaddresspool.yaml, this is git-tracked state ArgoCD reconciles against")


def apply_cluster_apps() -> None:
    for app in CLUSTER_APPS:
        path = K8S_DIR / "argocd-apps" / f"{app}.yaml"
        kubectl_run(["apply", "-f", str(path)])
    success(f"applied {len(CLUSTER_APPS)} cluster Applications — ArgoCD will reconcile Traefik/MetalLB/shared DBs from here")


def expose_argocd_ui() -> None:
    info("exposing ArgoCD's UI (plain HTTP, matching how Traefik fronts every other app here)...")
    kubectl_run(["patch", "cm", "argocd-cmd-params-cm", "-n", "argocd", "--type", "merge", "-p", '{"data":{"server.insecure":"true"}}'])
    kubectl_run(["rollout", "restart", "deployment", "argocd-server", "-n", "argocd"])
    kubectl_run(["apply", "-f", str(K8S_DIR / "cluster" / "argocd" / "lan-service.yaml")])
    success("ArgoCD UI will be reachable at http://localhost:18081 once the restart finishes")


def apply_secrets(skip: bool) -> None:
    env_path = K8S_DIR / ".env"
    if skip:
        warn("--skip-secrets passed, not running apply-secrets.py")
        return
    if not env_path.is_file():
        warn(f"{env_path} not found — copy kubernetes/.env.example to kubernetes/.env, fill in real values, then run: uv run kubernetes/apply-secrets.py")
        return
    info("running apply-secrets.py...")
    subprocess.run([sys.executable, str(K8S_DIR / "apply-secrets.py")], check=True)


def apply_service_apps() -> None:
    argocd_apps_dir = K8S_DIR / "argocd-apps"
    service_apps = sorted(p for p in argocd_apps_dir.glob("*.yaml") if not p.stem.startswith("cluster-"))
    info(f"applying {len(service_apps)} service Applications...")
    failures = []
    for path in service_apps:
        result = kubectl_run(["apply", "-f", str(path)], check=False)
        if result.returncode != 0:
            failures.append(path.stem)
    if failures:
        error(f"{len(failures)} Application(s) failed to apply: {', '.join(failures)}")
    else:
        success(f"all {len(service_apps)} service Applications applied")


def main() -> int:
    skip_secrets = "--skip-secrets" in sys.argv[1:]

    header("kubernetes/bootstrap.py — setting up the pilot cluster")
    check_prereqs()
    create_cluster()
    install_gateway_api_crds()
    apply_namespaces()
    bootstrap_argocd()
    fix_metallb_pool()
    apply_cluster_apps()
    expose_argocd_ui()
    apply_secrets(skip_secrets)
    apply_service_apps()

    header("Done")
    info("run `uv run kubernetes/k8s.py status` to see what's live")
    info("run `uv run kubernetes/k8s.py up min` to bring up the always-on baseline")
    info("configure Authentik's Proxy Provider + Application manually once authentik-server is up — that's live config, not a manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
