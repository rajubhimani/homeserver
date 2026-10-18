"""What Uptime Kuma should watch when the stack runs on Kubernetes.

Docker Container monitors read the Docker socket, which a Kubernetes pod
doesn't have, so every one of them reports "connect ENOENT /var/run/docker.sock".
The replacements, planned here from the generated manifests (no cluster needed):

- one HTTP monitor per public hostname (kubernetes/generated/envs/<env>/*/routes.yaml):
  the check a visitor's request makes, through Cloudflare, the tunnel and the router;
- one TCP monitor per database and cache (kubernetes/generated/apps/*): CloudNativePG
  `<name>-rw:5432`, MariaDB `<name>:3306`, and `*-redis` / `*-valkey` Services.

Monitors of services the env doesn't run are planned disabled, like the Docker
ones were for opt-in tiers. Pure functions, so a test can check the plan.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GENERATED = REPO_ROOT / "kubernetes" / "generated"

# 3xx: apps redirect to their login page (and authentik-protected hosts to
# authentik); 401: an app that answers "who are you" is alive.
ACCEPTED_STATUS = ["200-299", "300-399", "401"]
CACHE_SUFFIXES = ("-redis", "-valkey")


def running(env: str) -> set[str]:
    sys.path.insert(0, str(REPO_ROOT / "kubernetes"))
    from generate import running_services
    return running_services(env)


def _objects(path: Path):
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def plan(env: str = "prod", run: set[str] | None = None) -> list[dict]:
    """-> [{name, kind: http|tcp, url|hostname+port, active, service}], sorted by name."""
    run = running(env) if run is None else run
    out: list[dict] = []
    for f in sorted((GENERATED / "envs" / env).glob("*/routes.yaml")):
        svc = f.parent.name
        for d in _objects(f):
            # Redirect-only routes (www -> app host) answer 3xx by design; the
            # app's own host is already watched.
            if d.get("kind") != "HTTPRoute" or d["metadata"]["name"].endswith("-redirect"):
                continue
            for host in d["spec"]["hostnames"]:
                out.append({"name": host, "kind": "http", "url": f"https://{host}/",
                            "active": svc in run, "service": svc})
    for f in sorted((GENERATED / "apps").glob("*/*.yaml")):
        svc = f.parent.name
        for d in _objects(f):
            kind, name = d.get("kind"), (d.get("metadata") or {}).get("name", "")
            if kind == "Cluster" and d["apiVersion"].startswith("postgresql.cnpg.io"):
                target = (f"{name}-rw", 5432)
            elif kind == "MariaDB":
                target = (name, 3306)
            elif kind == "Service" and name.endswith(CACHE_SUFFIXES):
                target = (name, d["spec"]["ports"][0]["port"])
            else:
                continue
            out.append({"name": f"{name} (tcp)", "kind": "tcp", "hostname": target[0], "port": target[1],
                        "active": svc in run, "service": svc})
    names = [m["name"] for m in out]
    assert len(names) == len(set(names)), f"duplicate monitor names: {sorted(n for n in set(names) if names.count(n) > 1)}"
    return sorted(out, key=lambda m: m["name"])
