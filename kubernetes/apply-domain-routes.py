#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml"]
# ///
"""kubernetes/apply-domain-routes.py — creates a second HTTPRoute per
service pointing at your real domain (read from kubernetes/.env's
DOMAIN), alongside the existing git-managed *.k8s.local one.

Deliberately NOT tracked by ArgoCD: applied directly via kubectl under a
different object name (<name>-domain) than the git-managed route, with
no ArgoCD tracking-id annotation. If this patched the existing
git-managed HTTPRoute instead, ArgoCD's selfHeal would revert it back to
*.k8s.local on its next sync since the live object wouldn't match git —
a separate, ArgoCD-invisible object sidesteps that entirely. Same "real
value never committed, applied locally at runtime" pattern
apply-secrets.py already uses for Secrets — your real domain never has
to be committed to git the way every *.k8s.local hostname already is.

Discovers every service by reading its existing
kubernetes/apps/<service>/httproute.yaml (a file can hold more than one
HTTPRoute — e.g. firefly's importer sub-route) and cloning each one
verbatim (same parentRefs/rules/filters, including Authentik forward-auth
Middleware refs where present) with only the name and hostnames changed.

Usage:
  uv run kubernetes/apply-domain-routes.py                # every service with an httproute.yaml
  uv run kubernetes/apply-domain-routes.py <service> ...   # just these
"""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import yaml

K8S_DIR = Path(__file__).resolve().parent
APPS_DIR = K8S_DIR / "apps"
ENV_PATH = K8S_DIR / ".env"

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
RED = "\033[0;31m"
RESET = "\033[0m"


def info(msg: str) -> None:
    print(f"{CYAN}▶ {msg}{RESET}")


def success(msg: str) -> None:
    print(f"{GREEN}✔ {msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠ {msg}{RESET}")


def fail(msg: str) -> None:
    print(f"{RED}✖ {msg}{RESET}", file=sys.stderr)
    sys.exit(1)


def load_env_file(path: Path) -> dict[str, str]:
    """Same minimal KEY=VALUE parser convention as every other script
    here (apply-secrets.py, homeserver.py, ...)."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        result[key] = val
    return result


def domain_hostnames(hostnames: list[str], domain: str) -> list[str]:
    result = []
    for h in hostnames:
        if not h.endswith(".k8s.local"):
            warn(f"hostname '{h}' doesn't end in .k8s.local, leaving it out of the domain route")
            continue
        prefix = h[: -len(".k8s.local")]
        result.append(f"{prefix}.{domain}" if prefix else domain)
    return result


def build_domain_route(doc: dict, domain: str) -> dict | None:
    hostnames = doc.get("spec", {}).get("hostnames", [])
    new_hostnames = domain_hostnames(hostnames, domain)
    if not new_hostnames:
        return None
    new_doc = copy.deepcopy(doc)
    new_doc["metadata"]["name"] = f"{doc['metadata']['name']}-domain"
    new_doc["spec"]["hostnames"] = new_hostnames
    return new_doc


def kubectl_apply(doc: dict) -> bool:
    manifest = yaml.safe_dump(doc, sort_keys=False)
    result = subprocess.run(["kubectl", "apply", "-f", "-"], input=manifest, capture_output=True, text=True)
    if result.returncode != 0:
        warn(f"failed to apply {doc['metadata']['name']}: {result.stderr.strip()}")
        return False
    return True


def main() -> int:
    env = load_env_file(ENV_PATH)
    domain = env.get("DOMAIN", "").strip()
    if not domain or domain.startswith("your_"):
        fail("DOMAIN not set in kubernetes/.env — add DOMAIN=yourdomain.com (see kubernetes/.env.example)")

    args = sys.argv[1:]
    if args:
        targets = []
        for a in args:
            if not (APPS_DIR / a).is_dir():
                fail(f"unknown service '{a}' — no kubernetes/apps/{a}/ directory")
            targets.append(a)
    else:
        targets = sorted(p.name for p in APPS_DIR.iterdir() if p.is_dir() and (p / "httproute.yaml").is_file())

    if not targets:
        fail("no services with an httproute.yaml found under kubernetes/apps/")

    applied = 0
    skipped = 0
    failed = 0
    for service in targets:
        route_path = APPS_DIR / service / "httproute.yaml"
        if not route_path.is_file():
            warn(f"{service}: no httproute.yaml, skipping (not an HTTP-routed service)")
            skipped += 1
            continue
        docs = [d for d in yaml.safe_load_all(route_path.read_text(encoding="utf-8")) if d]
        for doc in docs:
            new_doc = build_domain_route(doc, domain)
            if new_doc is None:
                skipped += 1
                continue
            if kubectl_apply(new_doc):
                success(f"{new_doc['metadata']['name']}: {', '.join(new_doc['spec']['hostnames'])}")
                applied += 1
            else:
                failed += 1

    info(f"{applied} domain route(s) applied, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
