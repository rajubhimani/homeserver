#!/usr/bin/env python3
"""Start and stop services on Kubernetes like homeserver.py does on Docker.

    uv run kubernetes/k8s.py up     <min|core|daily|browser|office|automation-ai|all|group:<name>|service...> [--yes] [--dry-run]
    uv run kubernetes/k8s.py down   <same targets> [--yes] [--dry-run]
    uv run kubernetes/k8s.py status [targets]

Targets resolve exactly as homeserver.py resolves them (it's imported): 'up core'
also brings up MIN, 'up daily' MIN and CORE; 'down core' stops only CORE;
'down all' stops everything; group:<name> comes from services.json.

up    Secrets from .env, the shared database the service uses (started or
      resumed), the service itself, the local-access proxy; waits until ready.
down  Scales the service to 0 (volumes and data stay) and stops its own
      databases (CloudNativePG hibernation, mariadb-operator suspend). A shared
      database stops once no running service uses it, as on Docker.
      Phase 5 adds the backup homeserver.py takes on 'down'.

Only services in kubernetes/scope.yaml 'ported' can run; others are listed and
skipped. Hostnames: K8S_ENV in kubernetes/.env (test = *.k8s.local, prod = DOMAIN).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

K8S = Path(__file__).resolve().parent
REPO = K8S.parent
sys.path.insert(0, str(K8S))
sys.path.insert(0, str(REPO))
import homeserver as hs  # noqa: E402
from cluster import cfg, cmd_secrets, NAMESPACE  # noqa: E402
from generate import load_compose, load_overrides, load_scope, own_mariadb, own_postgres, shared_db_apps  # noqa: E402

TIERS = {
    "min": lambda: hs.SERVICES_MIN,
    "core": lambda: hs.SERVICES_MIN + hs.SERVICES_CORE,
    "daily": lambda: hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY,
    "browser": lambda: hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER,
    "office": lambda: hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER + hs.SERVICES_OFFICE,
    "automation-ai": lambda: (hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER
                              + hs.SERVICES_OFFICE + hs.SERVICES_AUTOMATION_AI),
    "all": lambda: (hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER + hs.SERVICES_OFFICE
                    + hs.SERVICES_AUTOMATION_AI + hs.SERVICES_EXTRA),
}
# 'down <tier>' stops only that tier (homeserver.py semantics); 'down all' everything.
DOWN_ONLY = {
    "min": lambda: hs.SERVICES_MIN, "core": lambda: hs.SERVICES_CORE, "daily": lambda: hs.SERVICES_DAILY,
    "browser": lambda: hs.SERVICES_BROWSER, "office": lambda: hs.SERVICES_OFFICE,
    "automation-ai": lambda: hs.SERVICES_AUTOMATION_AI, "all": TIERS["all"],
}
SHARED = {"postgres": "shared-postgres", "mariadb": "shared-mariadb"}


def resolve(tokens: list[str], action: str) -> tuple[list[str], bool]:
    """-> (services in order, expanded): the same targets homeserver.py accepts."""
    out, expanded = [], False
    for tok in tokens:
        if action == "down" and tok in DOWN_ONLY:
            out += DOWN_ONLY[tok]()
            expanded = True
        elif tok in TIERS:
            out += TIERS[tok]()
            expanded = True
        elif tok.startswith("group:"):
            name = tok[len("group:"):]
            if name not in hs.SERVICE_GROUPS:
                sys.exit(f"unknown group '{name}' (valid: {', '.join(sorted(hs.SERVICE_GROUPS))})")
            out += hs.SERVICE_GROUPS[name]
            expanded = True
        elif hs.is_valid_service(tok):
            out.append(tok)
        else:
            sys.exit(f"unknown service or target '{tok}'")
    seen, ordered = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    if action == "down" and any(t == "all" for t in tokens):
        ordered.reverse()  # like homeserver.py: stop in reverse order
    return ordered, expanded


class Kube:
    def __init__(self, dry: bool):
        self.dry = dry
        self.base = ["kubectl", "--context", f"kind-{cfg()['K8S_CLUSTER_NAME']}"]

    def run(self, *args: str, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess | None:
        cmd = self.base + list(args)
        if self.dry:
            print("  would run: kubectl " + " ".join(args))
            return None
        return subprocess.run(cmd, check=check, text=True, capture_output=quiet)

    def get(self, *args: str) -> dict:
        p = subprocess.run(self.base + list(args) + ["-o", "json"], capture_output=True, text=True)
        if p.returncode != 0:
            # Never report an unreachable API as "not deployed".
            sys.exit(f"kubectl failed: {p.stderr.strip()[:200]}")
        return json.loads(p.stdout) if p.stdout else {}


def own_databases(svc: str) -> list[tuple[str, str]]:
    """[(kind, name)] of the service's own operator-run databases."""
    ov = load_overrides(svc)
    out = []
    for n, s in (load_compose(svc).get("services") or {}).items():
        if (c := own_postgres(svc, n, s, ov)):
            out.append(("cluster", c["metadata"]["name"]))
        elif (m := own_mariadb(svc, n, s, ov)):
            out.append(("mariadb", m["metadata"]["name"]))
    return out


def start_db(k: Kube, kind: str, name: str) -> None:
    if kind == "cluster":  # CloudNativePG declarative hibernation off
        k.run("-n", NAMESPACE, "annotate", "cluster", name, "cnpg.io/hibernation-", check=False, quiet=True)
    else:  # mariadb-operator: resume reconciliation, which restores the replicas
        k.run("-n", NAMESPACE, "patch", "mariadb", name, "--type", "merge", "-p", '{"spec":{"suspend":false}}',
              check=False, quiet=True)
    k.run("-n", NAMESPACE, "wait", "--for=condition=Ready", f"{kind}/{name}", "--timeout=600s", check=False)


def stop_db(k: Kube, kind: str, name: str) -> None:
    if kind == "cluster":  # pods deleted, volumes kept (cloudnative-pg.io declarative_hibernation)
        k.run("-n", NAMESPACE, "annotate", "--overwrite", "cluster", name, "cnpg.io/hibernation=on")
    else:  # suspend (mariadb-operator docs: suspend), then stop its pods
        k.run("-n", NAMESPACE, "patch", "mariadb", name, "--type", "merge", "-p", '{"spec":{"suspend":true}}')
        k.run("-n", NAMESPACE, "scale", "statefulset", name, "--replicas=0", check=False)


def running(k: Kube, svc: str) -> bool:
    d = k.get("-n", NAMESPACE, "deployments,statefulsets", "-l", f"homeserver/service={svc}")
    return any((i.get("spec") or {}).get("replicas", 0) > 0 for i in d.get("items", []))


def up(k: Kube, services: list[str], env: str) -> None:
    shared = shared_db_apps()
    for svc in services:
        print(f"\n== up {svc}")
        spec = shared.get(svc)
        if spec:
            server = SHARED[spec["engine"]]
            if not k.dry:
                cmd_secrets(argparse.Namespace(services=[server], env=env))
            k.run("apply", "-k", str(K8S / "generated/envs" / env / server), quiet=True)
            start_db(k, "cluster" if spec["engine"] == "postgres" else "mariadb", server)
        if not k.dry:
            cmd_secrets(argparse.Namespace(services=[svc], env=env))
        k.run("apply", "-k", str(K8S / "generated/envs" / env / svc), quiet=True)
        for kind, name in own_databases(svc):
            start_db(k, kind, name)
        k.run("-n", NAMESPACE, "scale", "deployment", "-l", f"homeserver/service={svc}", "--replicas=1", check=False, quiet=True)
        for o in (k.get("-n", NAMESPACE, "deployments", "-l", f"homeserver/service={svc}").get("items") or []):
            k.run("-n", NAMESPACE, "rollout", "status", f"deployment/{o['metadata']['name']}", "--timeout=900s", check=False)
    k.run("apply", "-k", str(K8S / "generated/envs" / env / "local-access"), quiet=True)


def down(k: Kube, services: list[str]) -> None:
    shared = shared_db_apps()
    for svc in services:
        print(f"\n== down {svc}")
        k.run("-n", NAMESPACE, "scale", "deployment", "-l", f"homeserver/service={svc}", "--replicas=0", check=False)
        for kind, name in own_databases(svc):
            stop_db(k, kind, name)
    # Shared servers stop once no running service still uses them.
    for engine, server in SHARED.items():
        users = [s for s, spec in shared.items() if spec["engine"] == engine]
        still = [s for s in users if s not in services and running(k, s)]
        if still:
            print(f"{server} stays up: still used by {', '.join(still)}")
        elif any(s in services for s in users):
            print(f"no running service uses {server}: stopping it")
            stop_db(k, "cluster" if engine == "postgres" else "mariadb", server)


def status(k: Kube, services: list[str]) -> None:
    for svc in services:
        d = k.get("-n", NAMESPACE, "deployments,statefulsets", "-l", f"homeserver/service={svc}")
        items = d.get("items", [])
        ready = sum((i.get("status") or {}).get("readyReplicas", 0) or 0 for i in items)
        want = sum((i.get("spec") or {}).get("replicas", 0) for i in items)
        mark = "●" if want and ready == want else ("◐" if want else "○")
        print(f"  {mark} {svc:20} {ready}/{want} ready" if items else f"  ○ {svc:20} not deployed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["up", "down", "status"])
    ap.add_argument("targets", nargs="*")
    ap.add_argument("--yes", "-y", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--env", choices=["test", "prod"], help="hostnames (default: K8S_ENV in kubernetes/.env, else test)")
    a = ap.parse_args()
    env = a.env or cfg().get("K8S_ENV", "test")
    if not a.targets and a.action != "status":
        sys.exit("name a tier, group:<name> or service (see --help)")
    services, expanded = resolve(a.targets or ["all"], a.action)
    ported = set(load_scope().get("ported") or [])
    skipped = [s for s in services if s not in ported]
    services = [s for s in services if s in ported]
    if skipped:
        print("not on Kubernetes (scope.yaml): " + ", ".join(skipped))
    k = Kube(a.dry_run)
    if a.action == "status":
        status(k, services)
        return 0
    print(f"{a.action} ({env}): {', '.join(services)}")
    if expanded and not a.yes and not a.dry_run:
        if not sys.stdin.isatty() or input(f"{a.action} {len(services)} service(s)? [y/N] ").strip().lower() != "y":
            print("cancelled (use --yes to skip this question)")
            return 1
    (up(k, services, env) if a.action == "up" else down(k, services))
    return 0


if __name__ == "__main__":
    sys.exit(main())
