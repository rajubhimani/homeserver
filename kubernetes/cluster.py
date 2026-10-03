#!/usr/bin/env python3
"""Create and drive the kind test cluster that runs the generated manifests.

    uv run kubernetes/cluster.py create            # kind cluster from cluster/kind-config.template.yaml + kubernetes/.env
    uv run kubernetes/cluster.py install           # Gateway API, namespaces, Traefik, storage classes
    uv run kubernetes/cluster.py secrets [svc...]  # services/<svc>/.env -> Secret <svc>-env; root .env -> ConfigMap
    uv run kubernetes/cluster.py apply   [svc...]  # kubectl apply -k kubernetes/generated/envs/<env>/<svc>
    uv run kubernetes/cluster.py status
    uv run kubernetes/cluster.py delete            # remove the kind cluster (host data folders are kept)

Defaults to all ported services (kubernetes/scope.yaml) and --env test.
Versions come from kubernetes/versions.env, host paths/ports from
kubernetes/.env. Secrets are built in memory from each service's .env and
piped to kubectl: never written to disk or git. Guide: docs/17.
"""

from __future__ import annotations

import argparse
import json
import os
import string
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

K8S = Path(__file__).resolve().parent
REPO = K8S.parent
sys.path.insert(0, str(K8S))
from generate import load_env, load_scope  # noqa: E402

VERSIONS = load_env(K8S / "versions.env")
NAMESPACE = "apps"
TEST_DOMAIN = "k8s.local"


def cfg() -> dict[str, str]:
    env = K8S / ".env"
    if not env.is_file():
        sys.exit("kubernetes/.env missing: cp kubernetes/.env.example kubernetes/.env and adjust the paths")
    return {**VERSIONS, **load_env(env)}


def run(cmd: list[str], input: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    print("+ " + " ".join(cmd[:8]) + (" ..." if len(cmd) > 8 else ""), flush=True)
    return subprocess.run(cmd, input=input, text=True, check=check)


def kubectl(*args: str, input: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return run(["kubectl", "--context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", *args], input=input, check=check)


def services(names: list[str]) -> list[str]:
    ported = load_scope().get("ported") or []
    bad = [n for n in names if n not in ported]
    if bad:
        sys.exit(f"not ported yet (kubernetes/scope.yaml): {', '.join(bad)}")
    return names or ported


def cmd_create(_a) -> None:
    c = cfg()
    for key in ("K8S_FAST_PATH", "K8S_BULK_PATH", "K8S_IMAGES_PATH"):
        Path(c[key]).mkdir(parents=True, exist_ok=True)
    text = string.Template((K8S / "cluster/kind-config.template.yaml").read_text()).substitute(c)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(text)
    try:
        run(["kind", "create", "cluster", "--config", f.name, "--wait", "300s"])
    finally:
        os.unlink(f.name)


def cmd_install(_a) -> None:
    v = VERSIONS
    kubectl("apply", "--server-side", "-f",
            f"https://github.com/kubernetes-sigs/gateway-api/releases/download/{v['GATEWAY_API_VERSION']}/standard-install.yaml")
    kubectl("apply", "-f", str(K8S / "cluster/namespaces.yaml"))
    run(["helm", "--kube-context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "upgrade", "--install", "traefik", "traefik",
         "--repo", "https://traefik.github.io/charts", "--version", v["TRAEFIK_CHART_VERSION"],
         "--namespace", "infra", "-f", str(K8S / "cluster/traefik/values.yaml"), "--wait", "--timeout", "5m"])
    kubectl("apply", "-f", str(K8S / "cluster/traefik/gateway.yaml"))
    # kind's local-path provisioner: allow the fast/bulk folders, then the classes.
    conf = {"nodePathMap": [{"node": "DEFAULT_PATH_FOR_NON_LISTED_NODES",
                             "paths": ["/var/local-path-provisioner", "/var/k8s/fast", "/var/k8s/bulk"]}]}
    kubectl("-n", "local-path-storage", "patch", "configmap", "local-path-config", "--type", "merge",
            "-p", json.dumps({"data": {"config.json": json.dumps(conf, indent=1)}}))
    kubectl("apply", "-f", str(K8S / "cluster/storage.yaml"))


def secret_manifest(name: str, data: dict[str, str]) -> str:
    return yaml.safe_dump({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                           "metadata": {"name": name, "namespace": NAMESPACE,
                                        "labels": {"app.kubernetes.io/part-of": "homeserver"}},
                           "stringData": data})


def cmd_secrets(a) -> None:
    root = load_env(REPO / ".env")
    if a.env == "test":
        root["DOMAIN"] = TEST_DOMAIN  # apps build their own links for the test hostnames
    cm = {"apiVersion": "v1", "kind": "ConfigMap",
          "metadata": {"name": "homeserver-root", "namespace": NAMESPACE},
          "data": {"DOMAIN": root.get("DOMAIN", ""), "TZ": root.get("TZ", "Asia/Kolkata")}}
    kubectl("apply", "-f", "-", input=yaml.safe_dump(cm))
    prod_only = set(load_scope().get("prod_only") or [])
    for svc in services(a.services):
        env_file = REPO / "services" / svc / ".env"
        if a.env == "test" and svc in prod_only:
            continue  # e.g. cloudflared: its tunnel token never goes to the test cluster
        if env_file.is_file():
            kubectl("apply", "-f", "-", input=secret_manifest(f"{svc}-env", load_env(env_file)))


def cmd_apply(a) -> None:
    for svc in services(a.services):
        d = K8S / "generated/envs" / a.env / svc
        if not d.is_dir():
            print(f"skip {svc}: not rendered for env {a.env}")
            continue
        kubectl("apply", "-k", str(d))


def cmd_status(_a) -> None:
    kubectl("get", "pods,svc,pvc,httproute", "-n", NAMESPACE, "-o", "wide", check=False)


def cmd_delete(_a) -> None:
    run(["kind", "delete", "cluster", "--name", cfg()["K8S_CLUSTER_NAME"]])
    print("Host data folders (K8S_FAST_PATH/K8S_BULK_PATH/K8S_IMAGES_PATH) are kept; delete them by hand if wanted.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["create", "install", "secrets", "apply", "status", "delete"])
    ap.add_argument("services", nargs="*")
    ap.add_argument("--env", default="test", choices=["test", "prod"])
    a = ap.parse_args()
    {"create": cmd_create, "install": cmd_install, "secrets": cmd_secrets, "apply": cmd_apply,
     "status": cmd_status, "delete": cmd_delete}[a.action](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
