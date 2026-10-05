#!/usr/bin/env python3
"""Move the cluster's data into Docker (docs/17 "Going back to Docker").

Changes made on the cluster don't flow back by themselves: Docker only has its own
snapshots. This turns a `cluster.py export` into Docker's own snapshot format, so
`homeserver.py`'s tested restore does the loading, and adds the one step Docker's
snapshots don't have: an app with its OWN Postgres (the cluster exports a logical
dump of it, Docker keeps the raw data directory) gets that dump loaded into a fresh
database.

    uv run kubernetes/to_docker.py plan  --from-export DIR [svc...]   # what would happen; changes nothing
    uv run kubernetes/to_docker.py build --from-export DIR [svc...]   # write the snapshot folders only
    uv run kubernetes/to_docker.py load  --from-export DIR [svc...] --yes
                                          # restore into Docker (the service must not be running)

What maps to what:
  vol-<svc>-data.tar.gz        -> service_data/data/<svc>/   (the cluster's one volume per service mirrors DATA_ROOT)
  vol-<svc>-<key>.tar.gz       -> Docker volume <svc>_<key>   (a claim with no such Docker volume is a host folder
                                  there, e.g. Nextcloud's /mnt/seagate: skipped, its real folder is used directly)
  a shared-DB app's dump       -> <svc>_shareddb_<db>_<ts>.dump|.sql   (homeserver.py restore loads it)
  an own-DB app's dump         -> loaded here into a fresh database in that app's own Postgres container
Nothing is deleted: the old data stays in service_data/backup/ (Docker's own snapshots) and in the export.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Nothing worth carrying over: stateless, regenerated, or monitoring history that Docker's own copy covers.
SKIP = {
    "cloudflared": "no data", "docs": "stateless", "landing": "stateless", "nginx-plain": "stateless",
    "it-tools": "stateless", "whiteboard": "stateless", "clamav": "virus signatures: freshclam refetches them",
    "mailpit": "test mail only", "observability": "metrics and logs of the cluster, not of Docker",
    "uptime-kuma": "its monitors are Docker container monitors, which work again on Docker (its own data is kept)",
}
PG_IMAGES = re.compile(r"postgres|vchord|pgvecto|timescale", re.I)
MARIA_IMAGES = re.compile(r"mariadb|mysql", re.I)


# ── planning (pure) ──────────────────────────────────────────────────────

def docker_volume(svc: str, pvc: str) -> str | None:
    """The cluster's claim <svc>-<key> is Docker's volume <svc>_<key>; <svc>-data is the data folder."""
    if pvc == f"{svc}-data" or not pvc.startswith(svc + "-"):
        return None
    return f"{svc}_{pvc[len(svc) + 1:]}"


def snapshot_plan(svc: str, entry: dict, ts: str, shared: bool, compose_volumes: set[str],
                  sizes: dict[str, int] | None = None) -> dict:
    """-> {files: [(file in the export, name in the snapshot)], own_dbs: [db entries], notes: [str]}.
    `sizes` (export file -> bytes) lets a skipped volume say whether it held anything."""
    files, notes, own = [], [], []
    for v in entry.get("volumes", []):
        if v["pvc"] == f"{svc}-data":
            files.append((v["file"], f"service_data_{ts}.tar.gz"))
            continue
        dv = docker_volume(svc, v["pvc"])
        if dv and dv.split("_", 1)[1] in compose_volumes:
            files.append((v["file"], f"{dv}_{ts}.tar.gz"))
        else:
            n = (sizes or {}).get(v["file"])
            held = "" if n is None else (", empty" if n < 1024 else f", NOT EMPTY: {n / 1e6:.0f} MB, the cluster's copy of that folder")
            notes.append(f"{v['pvc']}: no Docker volume of that name, a host folder there: skipped, its real folder is used directly{held}")
    for d in entry.get("dbs", []):
        if shared:
            files.append((d["file"], f"{svc}_shareddb_{d['db']}_{ts}.{'dump' if d['engine'] == 'postgres' else 'sql'}"))
        else:
            own.append(d)
    return {"files": files, "own_dbs": own, "notes": notes}


def pick_db_container(dbs: list[dict], engine: str, db: str) -> dict | None:
    """The compose service that is this dump's database: the one whose POSTGRES_DB (MYSQL_DATABASE) is
    `db`, else the only one of that engine."""
    same = [d for d in dbs if d["engine"] == engine]
    named = [d for d in same if d.get("db") == db]
    return named[0] if named else (same[0] if len(same) == 1 else None)


def filter_toc(toc: str) -> tuple[str, list[str]]:
    """pg_restore -l output -> (the list without EXTENSION entries, the extension names).
    Extensions are created first as superuser; the rest is then restored without them."""
    exts = sorted({m.group(1) for ln in toc.splitlines() if not ln.startswith(";")
                   for m in [re.search(r" EXTENSION - (\S+)", ln)] if m})
    keep = "\n".join(ln for ln in toc.splitlines() if " EXTENSION - " not in ln and " COMMENT - EXTENSION " not in ln)
    return keep + "\n", exts


def render_plan(rows: list[dict]) -> str:
    out = []
    for r in rows:
        out.append(f"{r['svc']}: " + (f"SKIP ({r['skip']})" if r.get("skip") else
                   f"{len(r['plan']['files'])} file(s) into a snapshot" + (f", then {len(r['plan']['own_dbs'])} dump(s) into its own database" if r["plan"]["own_dbs"] else "")))
        out += [f"    note: {n}" for n in (r.get("plan") or {}).get("notes", [])]
    return "\n".join(out)


# ── Docker side (needs the repo's homeserver.py and Docker) ──────────────

def compose_info(svc: str) -> dict:
    """Resolved compose for a service: its volume keys and its database containers."""
    d = REPO / "services" / svc
    files = ["-f", "docker-compose.yml" if svc == "landing" else "compose.yml"]
    if (d / "compose.prod.yml").exists():
        files += ["-f", "compose.prod.yml"]
    env = {**os.environ, "DOMAIN": "x", "DATA_ROOT": "/tmp/x", "DOCKER_SOCKET": "/var/run/docker.sock"}
    p = subprocess.run(["docker", "compose", *files, "config", "--format", "json"], cwd=d, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"{svc}: docker compose config failed: {p.stderr.strip()[:200]}")
    cfg = json.loads(p.stdout)
    dbs = []
    for name, s in (cfg.get("services") or {}).items():
        image, e = s.get("image", ""), s.get("environment") or {}
        if PG_IMAGES.search(image) and "clickhouse" not in image:
            dbs.append({"service": name, "container": s.get("container_name") or name, "engine": "postgres",
                        "user": e.get("POSTGRES_USER", "postgres"), "db": e.get("POSTGRES_DB", e.get("POSTGRES_USER", "postgres"))})
        elif MARIA_IMAGES.search(image):
            dbs.append({"service": name, "container": s.get("container_name") or name, "engine": "mariadb",
                        "user": "root", "db": e.get("MARIADB_DATABASE", e.get("MYSQL_DATABASE", ""))})
    return {"volumes": set((cfg.get("volumes") or {}).keys()), "dbs": dbs, "services": list((cfg.get("services") or {}).keys())}


def load_postgres_dump(hs, container: str, user: str, db: str, dump: Path) -> bool:
    """Recreate `db` in the app's own Postgres container and load the cluster's dump into it:
    extensions first (as the container's superuser, the same role the app uses), then the rest
    without them, with ownership going to that role."""
    x = hs.BACKEND.db_exec

    def sql(q: str, dbname: str = "postgres") -> bool:
        ok, _, err = x(container, ["psql", "-U", user, "-d", dbname, "-v", "ON_ERROR_STOP=1", "-c", q])
        if not ok:
            print(f"    psql failed: {err.strip()[:200]}")
        return ok

    data = dump.read_bytes()
    ok, toc_b, err = x(container, ["sh", "-c", "cat > /tmp/restore.dump && pg_restore -l /tmp/restore.dump"], input=data)
    if not ok:
        print(f"    can't read the dump: {err.strip()[:200]}")
        return False
    keep, exts = filter_toc(toc_b.decode())
    if not (sql(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db}' AND pid <> pg_backend_pid()")
            and sql(f'DROP DATABASE IF EXISTS "{db}"') and sql(f'CREATE DATABASE "{db}" OWNER "{user}"')):
        return False
    for e in exts:
        if not sql(f'CREATE EXTENSION IF NOT EXISTS "{e}" CASCADE', db):
            return False
    ok, _, err = x(container, ["sh", "-c", "cat > /tmp/restore.list"], input=keep.encode())
    ok, _, err = x(container, ["pg_restore", "-U", user, "--no-owner", "--no-privileges", "-L", "/tmp/restore.list", "-d", db, "/tmp/restore.dump"])
    x(container, ["rm", "-f", "/tmp/restore.dump", "/tmp/restore.list"])
    # pg_restore exits non-zero on harmless warnings too: judge by what is actually there.
    ok2, out, _ = x(container, ["psql", "-U", user, "-d", db, "-tAc",
                                "select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema')"])
    tables = int(out.decode().strip() or 0) if ok2 else 0
    print(f"    {db}: {tables} tables loaded (extensions: {', '.join(exts) or 'none'})" + ("" if ok else f"; pg_restore said: {err.strip()[-160:]}"))
    return tables > 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["plan", "build", "load"])
    ap.add_argument("services", nargs="*")
    ap.add_argument("--from-export", required=True, help="a folder written by `cluster.py export`")
    ap.add_argument("--yes", action="store_true", help="load: actually restore into Docker")
    ap.add_argument("--env", default="prod", choices=["dev", "prod"])
    a = ap.parse_args()
    src = Path(a.from_export)
    manifest = json.loads((src / "export.json").read_text())
    ts = time_stamp()
    sys.path.insert(0, str(REPO))
    import homeserver as hs

    rows = []
    for svc in a.services or sorted(manifest):
        if svc not in manifest:
            sys.exit(f"{svc} is not in the export")
        if svc in SKIP:
            rows.append({"svc": svc, "skip": SKIP[svc]})
            continue
        info = compose_info(svc)
        sizes = {v["file"]: (src / svc / v["file"]).stat().st_size for v in manifest[svc].get("volumes", []) if (src / svc / v["file"]).exists()}
        plan = snapshot_plan(svc, manifest[svc], ts, bool(hs.shared_db_creds(svc)), info["volumes"], sizes)
        rows.append({"svc": svc, "plan": plan, "info": info})
    print(render_plan(rows))
    if a.action == "plan":
        return 0

    failed = []
    for r in rows:
        if r.get("skip"):
            continue
        svc, plan, info = r["svc"], r["plan"], r["info"]
        snap = hs.BACKUP_ROOT / svc / f"k8s-{ts}"
        snap.mkdir(parents=True, exist_ok=True)
        for fname, dest in plan["files"]:
            target = snap / dest
            if not target.exists():
                try:
                    os.link(src / svc / fname, target)  # same filesystem: no copy
                except OSError:
                    import shutil
                    shutil.copy2(src / svc / fname, target)
        if a.action == "build":
            print(f"{svc}: wrote {snap}")
            continue
        if not a.yes:
            sys.exit("load changes Docker's data: add --yes (run `plan` first)")
        print(f"\n== {svc}")
        shared = bool(hs.shared_db_creds(svc))
        if shared and not hs.shared_db_ready(svc, a.env, provision=False):
            failed.append(svc)
            continue
        if not hs.do_restore(svc, a.env, None, snapshot=snap.name):
            failed.append(svc)
            continue
        for d in plan["own_dbs"]:
            target = pick_db_container(info["dbs"], d["engine"], d["db"])
            if not target or d["engine"] != "postgres":
                print(f"    no matching {d['engine']} container for {d['db']}: load it by hand ({src / svc / d['file']})")
                failed.append(f"{svc}/{d['db']}")
                continue
            others = [s for s in info["services"] if s not in {x["service"] for x in info["dbs"]}]
            if not hs.do_up(svc, a.env, None, exclude=others):
                failed.append(svc)
                continue
            if not load_postgres_dump(hs, target["container"], target["user"], d["db"], src / svc / d["file"]):
                failed.append(f"{svc}/{d['db']}")
    if failed:
        print("\nNEEDS ATTENTION: " + ", ".join(failed))
        return 1
    return 0


def time_stamp() -> str:
    import time
    return time.strftime("%Y%m%d-%H%M%S")


if __name__ == "__main__":
    sys.exit(main())
