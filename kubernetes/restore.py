"""Plan for `cluster.py restore <service>`: put a service's data volumes back from a
Velero backup (the nightly file-system backup, kopia).

How Velero restores pod data (velero.io/docs/main/file-system-backup, "Restore"):
it restores the *pods*, injects a `restore-wait` init container, and a
PodVolumeRestore fills each volume; "Velero won't restore a resource if it is
scaled to 0 and already exists". So the service's workloads and PVCs are
deleted first (not scaled down), and the Restore re-creates them from the backup.

Nothing is thrown away: the old volume folder is moved aside on the node
(`restore-aside/`), and a fresh export is the other safety net. Databases are
not touched here (Postgres has Barman, shared-database apps their dumps).

Pure functions: the planner returns steps, `cluster.py` executes them, and the
tests check the plan without a cluster.
"""

from __future__ import annotations

from typing import NamedTuple

NAMESPACE = "apps"
VELERO_NS = "velero"
ASIDE = "/var/k8s/fast/restore-aside"  # on the kind node, next to the volume folders


class Step(NamedTuple):
    action: str  # pause | kubectl | wait_pods_gone | node_mv | velero_restore | wait_restore | unpause | wait_ready
    text: str    # what the owner reads in the plan
    args: tuple = ()


def restore_manifest(svc: str, backup: str, ts: str) -> dict:
    """The Velero Restore for one service's objects (selected by the label every
    generated object carries). Objects that still exist are skipped by default."""
    return {"apiVersion": "velero.io/v1", "kind": "Restore",
            "metadata": {"name": f"restore-{svc}-{ts}", "namespace": VELERO_NS,
                         "labels": {"app.kubernetes.io/part-of": "homeserver", "homeserver/service": svc}},
            "spec": {"backupName": backup, "includedNamespaces": [NAMESPACE],
                     "labelSelector": {"matchLabels": {"homeserver/service": svc}}}}


def plan(svc: str, backup: str, volumes: list[dict], ts: str) -> list[Step]:
    """volumes: [{pvc, pv, node_path}] — the service's own data volumes (never databases)."""
    sel = f"homeserver/service={svc}"
    steps = [
        Step("pause", f"Pause ArgoCD for {svc}, so it doesn't put the workloads back mid-restore"),
        Step("kubectl", f"Delete {svc}'s workloads (Velero skips what still exists, even scaled to 0)",
             ("-n", NAMESPACE, "delete", "deployments,statefulsets,daemonsets", "-l", sel, "--wait=true")),
        Step("wait_pods_gone", f"Wait until {svc}'s pods are gone", (sel,)),
    ]
    for v in volumes:
        steps += [
            Step("kubectl", f"Delete volume claim {v['pvc']}", ("-n", NAMESPACE, "delete", "pvc", v["pvc"], "--wait=true")),
            Step("kubectl", f"Delete its released volume {v['pv']}", ("delete", "pv", v["pv"], "--wait=true")),
            Step("node_mv", f"Move the old data aside, not deleted: {v['node_path']} -> {ASIDE}/{v['pvc']}.{ts}",
                 (v["node_path"], f"{ASIDE}/{v['pvc']}.{ts}")),
        ]
    steps += [
        Step("velero_restore", f"Velero restores {svc} from backup {backup} (objects and volume data)", (svc, backup, ts)),
        Step("wait_restore", "Wait for the restore and every PodVolumeRestore to finish", (f"restore-{svc}-{ts}",)),
        Step("unpause", "Resume ArgoCD: it recreates anything the restore didn't bring back"),
        Step("wait_ready", f"Wait for {svc}'s workloads to be ready", (sel,)),
    ]
    return steps


def render(svc: str, backup: str, steps: list[Step], yes: bool) -> str:
    lines = [f"restore {svc} from Velero backup {backup}:"]
    lines += [f"  {i}. {s.text}" for i, s in enumerate(steps, 1)]
    if not yes:
        lines.append("\nDry run: nothing was changed. Add --yes to run it. Take a fresh `cluster.py export` first.")
    return "\n".join(lines)
