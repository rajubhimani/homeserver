#!/usr/bin/env python3
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

Pure stdlib, no YAML library: every kubernetes/apps/*/httproute.yaml in
this repo (verified against all of them) follows one exact, uniform
shape — `metadata:` immediately followed by its `name:` line, and
`hostnames:` immediately followed by exactly one quoted `*.k8s.local`
entry. Rather than parse+re-serialize full YAML (which pulls in a
dependency whose C extension has been observed to crash outright with
an access violation on at least one real Windows machine, with zero
error output), this does two targeted text substitutions on each
document's own raw text and leaves everything else — parentRefs, rules,
filters like Authentik's forward-auth Middleware ref, comments,
formatting — byte-identical to the original.

Usage:
  uv run kubernetes/apply-domain-routes.py                # every service with an httproute.yaml
  uv run kubernetes/apply-domain-routes.py <service> ...   # just these
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

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


NAME_RE = re.compile(r"^(metadata:\n(?:[ \t]*\n)*[ \t]*name:[ \t]*)(\S+)(\n)", re.MULTILINE)
HOSTNAME_RE = re.compile(r'^([ \t]*hostnames:\n[ \t]*- ")([^"]+)("\n)', re.MULTILINE)


def build_domain_route_text(doc_text: str, domain: str) -> tuple[str, str, str] | None:
    """Returns (new_doc_text, new_name, new_hostname), or None if this
    document doesn't match the expected shape (e.g. no *.k8s.local
    hostname to translate)."""
    name_match = NAME_RE.search(doc_text)
    host_match = HOSTNAME_RE.search(doc_text)
    if not name_match or not host_match:
        return None
    old_hostname = host_match.group(2)
    if not old_hostname.endswith(".k8s.local"):
        return None
    prefix = old_hostname[: -len(".k8s.local")]
    new_hostname = f"{prefix}.{domain}" if prefix else domain
    new_name = f"{name_match.group(2)}-domain"

    new_text = doc_text[: name_match.start()] + name_match.group(1) + new_name + name_match.group(3) + doc_text[name_match.end() :]
    # Re-locate the hostname match against the mutated text (the name
    # substitution shifted offsets) rather than reuse the original match.
    host_match = HOSTNAME_RE.search(new_text)
    new_text = new_text[: host_match.start()] + host_match.group(1) + new_hostname + host_match.group(3) + new_text[host_match.end() :]
    return new_text, new_name, new_hostname


def kubectl_apply(manifest_text: str, name: str) -> bool:
    result = subprocess.run(["kubectl", "apply", "-f", "-"], input=manifest_text, capture_output=True, text=True)
    if result.returncode != 0:
        warn(f"failed to apply {name}: {result.stderr.strip()}")
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
        content = route_path.read_text(encoding="utf-8")
        docs = re.split(r"\n---[ \t]*\n", content)
        for doc_text in docs:
            if "kind: HTTPRoute" not in doc_text:
                continue
            result = build_domain_route_text(doc_text, domain)
            if result is None:
                warn(f"{service}: a document in httproute.yaml didn't match the expected shape, skipping it")
                skipped += 1
                continue
            new_text, new_name, new_hostname = result
            if kubectl_apply(new_text, new_name):
                success(f"{new_name}: {new_hostname}")
                applied += 1
            else:
                failed += 1

    info(f"{applied} domain route(s) applied, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
