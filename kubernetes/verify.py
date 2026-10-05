"""Post-rebuild / daily health check for the cluster: `cluster.py verify`.

Everything the 2026-10-04/05 rebuilds had to check by hand, in one place: nodes,
pods, ArgoCD apps, databases, backups, the tunnel and the public hostnames, plus
the host's own disk. Pure functions over injected helpers (`kg` = kubectl get ->
list of objects, `http` = url -> status code), so tests can feed fake states.

What it can't see: the public hostnames are fetched from THIS machine, which
reaches Cloudflare through its nearest edge. On 2026-10-05 the tunnel passed
there and returned `530 / error code: 1033` everywhere else for ~20 minutes
(fixed by restarting cloudflared). Check from another network as well.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

MAX_BACKUP_AGE_H = 36  # nightly + a late-running night
HTTP_UP = range(200, 400)


def _age_h(ts: str | None) -> float:
    if not ts:
        return 1e9
    t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600


def _ready(obj: dict) -> bool:
    return any(c.get("type") == "Ready" and c.get("status") == "True" for c in (obj.get("status") or {}).get("conditions") or [])


def verify_checks(run: set[str], ported: set[str], kg, http, tunnel_ready, urls: list[str],
                  host: dict | None = None) -> list[tuple[str, bool, str]]:
    """-> [(check, ok, detail)]. `run`: services the env runs; `ported`: all
    ported services (the rest of `ported` are stopped on purpose, so their
    ArgoCD apps and pods don't count)."""
    out: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        out.append((name, bool(ok), detail))

    nodes = kg("nodes")
    bad = [n["metadata"]["name"] for n in nodes if not _ready(n)]
    add("nodes ready", nodes and not bad, f"not ready: {bad}" if bad else f"{len(nodes)} node(s)")

    pods = kg("pods", "-A")
    broken = []
    for p in pods:
        phase = (p.get("status") or {}).get("phase")
        if phase == "Succeeded":
            continue
        if phase != "Running" or not _ready(p):
            broken.append(f"{p['metadata']['namespace']}/{p['metadata']['name']} ({phase})")
    add("pods running and ready", not broken, ", ".join(broken[:6]) + (f" ... +{len(broken) - 6}" if len(broken) > 6 else "")
        if broken else f"{len(pods)} pods")

    stopped = ported - run
    apps = kg("applications.argoproj.io", "-n", "argocd")
    sick = [a["metadata"]["name"] for a in apps
            if a["metadata"]["name"] not in stopped
            and ((a.get("status") or {}).get("sync", {}).get("status") != "Synced"
                 or (a.get("status") or {}).get("health", {}).get("status") != "Healthy")]
    add("ArgoCD apps synced and healthy", apps and not sick, f"not ok: {sick[:8]}" if sick else f"{len(apps)} apps")

    pg = kg("clusters.postgresql.cnpg.io", "-A")
    pg_bad = [c["metadata"]["name"] for c in pg if (c.get("status") or {}).get("phase") != "Cluster in healthy state"
              or (c.get("status") or {}).get("readyInstances") != (c.get("spec") or {}).get("instances")]
    add("Postgres clusters healthy", pg and not pg_bad, f"not healthy: {pg_bad}" if pg_bad else f"{len(pg)} clusters")
    my = kg("mariadbs.k8s.mariadb.com", "-A")
    my_bad = [m["metadata"]["name"] for m in my if not _ready(m)]
    add("MariaDB servers ready", not my_bad, f"not ready: {my_bad}" if my_bad else f"{len(my)} servers")

    bsl = kg("backupstoragelocations.velero.io", "-n", "velero")
    add("backup store reachable (Velero)", bsl and all((b.get("status") or {}).get("phase") == "Available" for b in bsl),
        ", ".join(f"{b['metadata']['name']}={(b.get('status') or {}).get('phase')}" for b in bsl) or "no BackupStorageLocation")
    vb = [b for b in kg("backups.velero.io", "-n", "velero") if (b.get("status") or {}).get("completionTimestamp")]
    last = max(vb, key=lambda b: b["status"]["completionTimestamp"], default=None)
    add("Velero backup recent and clean",
        last and last["status"].get("phase") == "Completed" and _age_h(last["status"]["completionTimestamp"]) < MAX_BACKUP_AGE_H,
        f"{last['metadata']['name']}: {last['status'].get('phase')}, {_age_h(last['status']['completionTimestamp']):.0f} h old"
        if last else "no completed backup yet")
    cb = kg("backups.postgresql.cnpg.io", "-A")
    stale = []
    for c in pg:
        mine = [b for b in cb if (b.get("spec") or {}).get("cluster", {}).get("name") == c["metadata"]["name"]
                and (b.get("status") or {}).get("phase") == "completed"]
        newest = max((b["status"].get("stoppedAt") for b in mine if b["status"].get("stoppedAt")), default=None)
        if newest is None or _age_h(newest.split(".")[0].rstrip("Z") + "Z") >= MAX_BACKUP_AGE_H:
            stale.append(c["metadata"]["name"])
    add("Postgres base backups recent", pg and not stale, f"no recent backup: {stale}" if stale else f"{len(pg)} clusters")

    if "cloudflared" in run:
        dep = [d for d in kg("deployments", "-n", "apps") if d["metadata"]["name"] == "cloudflared"]
        ready = dep and (dep[0].get("status") or {}).get("readyReplicas") == 1
        add("tunnel pod ready", ready, "" if ready else "cloudflared deployment not ready")
        connected = bool(ready) and tunnel_ready()
        add("tunnel connected to Cloudflare", connected, "" if connected else "`cloudflared tunnel ready` failed")
    down = []
    for u in urls:
        code = http(u)
        if code not in HTTP_UP and code != 401:
            down.append(f"{u.split('//')[1].rstrip('/')} ({code})")
    add("public hostnames answer (from this machine)", urls and not down,
        f"failing: {down[:6]}" if down else f"{len(urls)} hostnames (also test from another network)")

    for name, h in (host or {}).items():
        add(f"host: {name}", h[0], h[1])
    return out


def host_checks(root: Path = Path("/")) -> dict[str, tuple[bool, str]]:
    """The host-level things that took this stack down before: SATA link power
    saving (docs/08 'System freezes'), disk I/O pressure, free space."""
    out: dict[str, tuple[bool, str]] = {}
    # Only ports with a disk behind them (device/target*): empty ports keep the firmware setting.
    pols = {p.read_text().strip() for p in (root / "sys/class/scsi_host").glob("host*/link_power_management_policy")
            if any((p.parent / "device").glob("target*"))}
    if pols:
        out["SATA link power = max_performance"] = (pols == {"max_performance"}, ", ".join(sorted(pols)))
    psi = root / "proc/pressure/io"
    if psi.is_file():
        full = dict(kv.split("=") for kv in psi.read_text().splitlines()[1].split()[1:])
        out["disk I/O pressure (full, 5 min) < 30%"] = (float(full["avg300"]) < 30, f"{full['avg300']}%")
    import shutil
    for mount in ("/home", "/mnt/mydata"):
        if Path(mount).exists():
            u = shutil.disk_usage(mount)
            out[f"free space on {mount} > 15%"] = (u.free / u.total > 0.15, f"{u.free / u.total:.0%} free")
    return out


def render(results: list[tuple[str, bool, str]]) -> str:
    width = max(len(n) for n, _, _ in results)
    lines = [f"  {'OK ' if ok else 'FAIL'}  {name.ljust(width)}  {detail}" for name, ok, detail in results]
    failed = sum(not ok for _, ok, _ in results)
    lines.append(f"\n{len(results) - failed}/{len(results)} checks passed" + (f", {failed} FAILED" if failed else ""))
    return "\n".join(lines)
