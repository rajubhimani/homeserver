#!/usr/bin/env python3
"""Start and stop services on Kubernetes the GitOps way: edit the running list
in kubernetes/deploy/<env>.yaml, which ArgoCD applies from git.

    uv run kubernetes/k8s.py up     <min|core|daily|browser|office|automation-ai|all|group:<name>|service...> [--env E]
    uv run kubernetes/k8s.py down   <same targets> [--env E]
    uv run kubernetes/k8s.py status [targets] [--env E]

Targets mean what they mean to homeserver.py (kubernetes/targets.py): 'up core'
also runs MIN, 'down core' stops only CORE, 'down all' stops everything,
group:<name> comes from services.json.

up/down change the file and re-render kubernetes/generated/ (generate.py).
Nothing changes in the cluster until you commit and push: ArgoCD then applies
it (by itself with auto_sync: true, else with Sync in its UI). Volumes and
databases stay when a service stops; a shared database stops once no running
service uses it, as on Docker. status compares git with the cluster.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

K8S = Path(__file__).resolve().parent
sys.path.insert(0, str(K8S))
from cluster import NAMESPACE, cfg  # noqa: E402
from generate import DEPLOY_DIR, load_deploy, load_scope, running_services  # noqa: E402
from targets import TargetError, resolve  # noqa: E402


def save_deploy(env: str, d: dict) -> None:
    """Rewrite the lists in place, keeping the file's comments."""
    f = DEPLOY_DIR / f"{env}.yaml"
    lines = f.read_text().splitlines()
    for key in ("running", "stopped"):
        val = "[" + ", ".join(d.get(key) or []) + "]"
        lines = [f"{key}: {val}" if ln.startswith(f"{key}:") else ln for ln in lines]
    f.write_text("\n".join(lines) + "\n")


def edit(env: str, action: str, tokens: list[str]) -> tuple[set[str], set[str]]:
    """-> (running before, running after)."""
    d = load_deploy(env)
    before = running_services(env)
    running, stopped = list(d.get("running") or []), list(d.get("stopped") or [])
    if action == "up":
        svcs, _ = resolve(tokens, "up")
        for tok in tokens:
            if tok not in running:
                running.append(tok)
        stopped = [s for s in stopped if s not in svcs]
    else:
        svcs, _ = resolve(tokens, "down")
        running = [r for r in running if r not in tokens]
        still, _ = resolve(running, "up") if running else ([], False)
        stopped += [s for s in svcs if s in still and s not in stopped]
    d["running"], d["stopped"] = running, stopped
    save_deploy(env, d)
    return before, running_services(env)


def live(svc: str) -> tuple[int, int, int]:
    """(workloads, wanted pods, ready pods) for a service in the cluster."""
    p = subprocess.run(["kubectl", "--context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "-n", NAMESPACE, "get",
                        "deployments,daemonsets", "-l", f"homeserver/service={svc}", "-o", "json"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"kubectl failed: {p.stderr.strip()[:200]}")  # never report an unreachable API as "stopped"
    items = json.loads(p.stdout).get("items", [])
    want = sum((i["spec"].get("replicas", 0) if i["kind"] == "Deployment"
                else (i.get("status") or {}).get("desiredNumberScheduled", 0)) for i in items)
    ready = sum((i.get("status") or {}).get("readyReplicas" if i["kind"] == "Deployment" else "numberReady", 0) or 0
                for i in items)
    return len(items), want, ready


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["up", "down", "status"])
    ap.add_argument("targets", nargs="*")
    ap.add_argument("--env", choices=["test", "prod"], help="default: K8S_ENV in kubernetes/.env, else test")
    a = ap.parse_args()
    env = a.env or cfg().get("K8S_ENV", "test")
    if not a.targets and a.action != "status":
        sys.exit("name a tier, group:<name> or service (see --help)")
    try:
        if a.action == "status":
            svcs, _ = resolve(a.targets or ["all"], "up")
            ported = load_scope().get("ported") or []
            git = running_services(env)
            print(f"git ({env}) vs cluster:")
            for svc in [s for s in svcs if s in ported] + sorted({"shared-postgres", "shared-mariadb"} & git):
                n, want, ready = live(svc)
                mark = "●" if want and ready == want else ("◐" if want else "○")
                state = "running" if svc in git else "stopped"
                print(f"  {mark} {svc:20} git: {state:8} cluster: {ready}/{want} ready" if n
                      else f"  ○ {svc:20} git: {state:8} cluster: not deployed")
            return 0
        before, after = edit(env, a.action, a.targets)
    except TargetError as e:
        sys.exit(str(e))
    on, off = sorted(after - before), sorted(before - after)
    skipped = [s for s in resolve(a.targets, a.action)[0] if s not in (load_scope().get("ported") or [])]
    if skipped:
        print("not on Kubernetes (scope.yaml): " + ", ".join(skipped))
    print(f"kubernetes/deploy/{env}.yaml: " + ("; ".join(filter(None, [
        "starts " + ", ".join(on) if on else "", "stops " + ", ".join(off) if off else ""])) or "no change"))
    if on or off:
        subprocess.run([sys.executable, str(K8S / "generate.py")], check=True)
        print("Next: commit and push kubernetes/deploy/ and kubernetes/generated/; ArgoCD applies it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
