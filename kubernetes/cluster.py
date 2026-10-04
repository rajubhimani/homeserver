#!/usr/bin/env python3
"""Create and drive the kind test cluster that runs the generated manifests.

    uv run kubernetes/cluster.py create            # kind cluster from cluster/kind-config.template.yaml + kubernetes/.env
    uv run kubernetes/cluster.py install           # Gateway API, namespaces, Traefik, storage classes, DB operators
    uv run kubernetes/cluster.py secrets [svc...]  # services/<svc>/.env -> Secret <svc>-env; root .env -> ConfigMap
    uv run kubernetes/cluster.py apply   [svc...]  # kubectl apply -k kubernetes/generated/envs/<env>/<svc>
    uv run kubernetes/cluster.py import  <svc...> [--snapshot TS]  # copy a Compose snapshot's data into the cluster
    uv run kubernetes/cluster.py validate [svc...]   # server-side dry run: the API server checks every manifest, nothing is created
    uv run kubernetes/cluster.py status
    uv run kubernetes/cluster.py delete            # remove the kind cluster (host data folders are kept)

Defaults to all ported services (kubernetes/scope.yaml) and --env test.
Versions come from kubernetes/versions.env, host paths/ports from
kubernetes/.env. Secrets are built in memory from each service's .env and
piped to kubectl: never written to disk or git. Guide: docs/17.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
from generate import load_compose, load_env, load_overrides, load_scope, own_db_keys, own_mariadb, own_postgres, shared_db_apps, slug  # noqa: E402

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
    # Host folders services read from (overrides with hostPath + env): the
    # real path from that service's .env, at the fixed node path the
    # generated manifests use. kind can only add mounts at create time.
    # Compose's localhost ports (generated/host-ports.yaml), on 127.0.0.1 like Compose's prod files.
    hp = yaml.safe_load((K8S / "generated/host-ports.yaml").read_text()) or []
    text = text.replace("    extraMounts:\n", "".join(
        f"      - containerPort: {e['node']}\n        hostPort: {e['host']}\n        listenAddress: \"127.0.0.1\"\n"
        f"        protocol: {e['protocol'].upper()}\n" for e in hp) + "    extraMounts:\n", 1)
    ports = node_ports()
    if ports:
        # Ports host-network services receive straight from outside (the
        # WireGuard VPN): forwarded from every host interface into the node.
        maps = "".join(f"      - containerPort: {pt}\n        hostPort: {pt}\n        protocol: {proto.upper()}\n"
                       for pt, proto in ports)
        text = text.replace("    extraMounts:\n", maps + "    extraMounts:\n", 1)
    for node_path, host, ro in host_mounts():
        text += (f"      - hostPath: {host}\n        containerPath: {node_path}\n"
                 + ("        readOnly: true\n" if ro else ""))
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(text)
    try:
        run(["kind", "create", "cluster", "--config", f.name, "--wait", "300s"])
    finally:
        os.unlink(f.name)


def host_mounts() -> list[tuple[str, str, bool]]:
    """[(node path, host path, read-only)] from every ported service's
    overrides; the host path is the .env value Compose uses. Read-only into
    the node only if every container mounting it is :ro in Compose (e.g.
    nextcloud writes OS_ISO_ROOT, nextcloud-cron only reads it)."""
    out: dict[str, tuple[str, bool]] = {}
    for svc in load_scope().get("ported") or []:
        compose = load_compose(svc)["services"]
        for cname, co in (load_overrides(svc).get("containers") or {}).items():
            s = next((s for n, s in compose.items() if (s.get("container_name") or n) == cname), {})
            for tgt, mo in (co.get("mounts") or {}).items():
                if mo.get("hostPath") and mo.get("env"):
                    host = host_path(svc, mo["env"])
                    if not Path(host).is_dir():
                        sys.exit(f"{svc}: {mo['env']}={host} is not a folder on this host")
                    ro = any(m.get("target") == tgt and m.get("read_only") for m in s.get("volumes") or [])
                    prev = out.get(mo["hostPath"], (host, True))
                    out[mo["hostPath"]] = (host, prev[1] and ro)
    return [(k, v[0], v[1]) for k, v in sorted(out.items())]


def node_ports() -> list[tuple[int, str]]:
    """[(port, protocol)] from every ported service's overrides (node_ports)."""
    out = set()
    for svc in load_scope().get("ported") or []:
        for co in (load_overrides(svc).get("containers") or {}).values():
            for np in co.get("node_ports") or []:
                out.add((int(np["port"]), np.get("protocol", "tcp")))
    return sorted(out)


def host_path(svc: str, key: str) -> str:
    """A path from services/<svc>/.env, resolved like Compose does (relative
    to the service folder)."""
    val = load_env(REPO / "services" / svc / ".env").get(key, "")
    if not val:
        sys.exit(f"{svc}: {key} isn't set in services/{svc}/.env")
    return str((REPO / "services" / svc / val).resolve())


def cmd_install(_a) -> None:
    v = VERSIONS
    kubectl("apply", "--server-side", "-f",
            f"https://github.com/kubernetes-sigs/gateway-api/releases/download/{v['GATEWAY_API_VERSION']}/standard-install.yaml")
    kubectl("apply", "-f", str(K8S / "cluster/namespaces.yaml"))
    run(["helm", "--kube-context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "upgrade", "--install", "traefik", "traefik",
         "--repo", "https://traefik.github.io/charts", "--version", v["TRAEFIK_CHART_VERSION"],
         "--namespace", "infra", "-f", str(K8S / "cluster/traefik/values.yaml"), "--wait", "--timeout", "5m"])
    # kind's local-path provisioner: allow the fast/bulk folders, then the classes.
    conf = {"nodePathMap": [{"node": "DEFAULT_PATH_FOR_NON_LISTED_NODES",
                             "paths": ["/var/local-path-provisioner", "/var/k8s/fast", "/var/k8s/bulk"]}]}
    kubectl("-n", "local-path-storage", "patch", "configmap", "local-path-config", "--type", "merge",
            "-p", json.dumps({"data": {"config.json": json.dumps(conf, indent=1)}}))
    kubectl("apply", "-f", str(K8S / "cluster/storage.yaml"))
    # Database operators: CloudNativePG (shared + own Postgres) and
    # mariadb-operator (shared MariaDB). Both watch every namespace.
    kubectl("apply", "--server-side", "-f",
            f"https://github.com/cloudnative-pg/cloudnative-pg/releases/download/v{v['CNPG_VERSION']}/cnpg-{v['CNPG_VERSION']}.yaml")
    kubectl("-n", "cnpg-system", "rollout", "status", "deployment/cnpg-controller-manager", "--timeout=5m")
    for chart in ("mariadb-operator-crds", "mariadb-operator"):
        run(["helm", "--kube-context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "upgrade", "--install", chart, chart,
             "--repo", "https://helm.mariadb.com/mariadb-operator", "--version", v["MARIADB_OPERATOR_VERSION"],
             "--namespace", "mariadb-operator", "--create-namespace", "--wait", "--timeout", "5m"])


def env_hash(data: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def secret_manifest(name: str, data: dict[str, str], kind: str = "Opaque", labels: dict | None = None) -> str:
    return yaml.safe_dump({"apiVersion": "v1", "kind": "Secret", "type": kind,
                           "metadata": {"name": name, "namespace": NAMESPACE,
                                        "labels": {"app.kubernetes.io/part-of": "homeserver", **(labels or {})},
                                        "annotations": {"homeserver/env-sha256": env_hash(data)}},
                           "stringData": data})


def current_hash(name: str) -> str | None:
    """The env hash on the Secret in the cluster, or None if it doesn't exist."""
    p = subprocess.run(["kubectl", "--context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "-n", NAMESPACE, "get", "secret",
                        name, "-o", "jsonpath={.metadata.annotations.homeserver/env-sha256}"],
                       capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def basic_auth(name: str, user: str, password: str) -> str:
    """CNPG reads logins from kubernetes.io/basic-auth Secrets; the reload
    label makes it apply a changed password (rotation = edit .env, re-run)."""
    return secret_manifest(name, {"username": user, "password": password},
                           "kubernetes.io/basic-auth", {"cnpg.io/reload": "true"})


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
        if not env_file.is_file():
            continue
        env = load_env(env_file)
        spec = shared_db_apps().get(svc)
        # mariadb-operator re-reads a password Secret only when it carries
        # this label (User.passwordSecretKeyRef docs), so rotation = edit .env.
        watch = {"k8s.mariadb.com/watch": ""} if svc == "shared-mariadb" or (spec and spec["engine"] == "mariadb") else None
        before = current_hash(f"{svc}-env")
        kubectl("apply", "-f", "-", input=secret_manifest(f"{svc}-env", env, labels=watch))
        # (Operator-run servers are left to their operator.)
        if before and before != env_hash(env) and svc not in ("shared-postgres", "shared-mariadb"):
            # Pods read env only at start: restart this service's workloads,
            # the kubectl form of Helm's documented checksum/config roll.
            kubectl("rollout", "restart", "deployment,statefulset,daemonset", "-n", NAMESPACE,
                    "-l", f"homeserver/service={svc}", check=False)
        if svc == "shared-postgres":
            kubectl("apply", "-f", "-", input=basic_auth(f"{svc}-superuser", env.get("POSTGRES_USER", "postgres"),
                                                         env.get("POSTGRES_PASSWORD", "")))
        if (own := own_db_keys(svc)):
            # A CORE app's own CNPG cluster: its database owner login.
            # (<svc>-db-superuser for apps that log in as postgres.)
            user = env.get(own["user_key"], own["user"]) if own["user_key"] else own["user"]
            kubectl("apply", "-f", "-", input=basic_auth(own["secret"], user, env.get(own["password_key"], "")))
        if spec and spec["engine"] == "postgres":
            # Same values homeserver.py's shared_db_creds reads from this .env.
            val = lambda k: k[1:] if k.startswith("=") else env.get(k, "")  # noqa: E731
            kubectl("apply", "-f", "-", input=basic_auth(f"{svc}-db-role", val(spec["user_key"]),
                                                         val(spec["password_key"])))


def cmd_apply(a) -> None:
    for svc in services(a.services):
        d = K8S / "generated/envs" / a.env / svc
        if not d.is_dir():
            print(f"skip {svc}: not rendered for env {a.env}")
            continue
        kubectl("apply", "-k", str(d))


def snapshot_dir(svc: str, ts: str | None) -> Path | None:
    """The service's newest regular Compose snapshot (timestamp-named folders
    only, as homeserver.py's restore picks them), or the one asked for."""
    root = REPO / "service_data/backup" / svc
    snaps = sorted(d.name for d in root.glob("*") if d.is_dir() and d.name[:8].isdigit()) if root.is_dir() else []
    if ts:
        if ts not in snaps and not (root / ts).is_dir():
            sys.exit(f"{svc}: no snapshot {ts} in {root}")
        return root / ts
    if not snaps:
        return None  # e.g. clamav: no data, only copy_from folders
    return root / snaps[-1]


def pvc_host_path(pvc: str) -> Path:
    """Host folder behind a bound PVC (kind node paths -> kubernetes/.env paths)."""
    c = cfg()
    p = subprocess.run(["kubectl", "--context", f"kind-{c['K8S_CLUSTER_NAME']}", "-n", NAMESPACE, "get", "pvc", pvc,
                        "-o", "jsonpath={.spec.volumeName}"], capture_output=True, text=True)
    pv = p.stdout.strip()
    if not pv:
        sys.exit(f"PVC {pvc} isn't bound yet: apply the service first and let its pod start once")
    q = subprocess.run(["kubectl", "--context", f"kind-{c['K8S_CLUSTER_NAME']}", "get", "pv", pv, "-o",
                        "jsonpath={.spec.hostPath.path}{.spec.local.path}"], capture_output=True, text=True)
    node = q.stdout.strip()
    for prefix, key in (("/var/k8s/fast", "K8S_FAST_PATH"), ("/var/k8s/bulk", "K8S_BULK_PATH")):
        if node.startswith(prefix):
            return Path(os.path.expanduser(c[key])) / node[len(prefix):].lstrip("/")
    sys.exit(f"PV {pv} lives at {node}, outside the fast/bulk folders")


def has_pvc(svc: str, name: str) -> bool:
    """Whether the generated manifests declare this PVC for the service."""
    f = K8S / "generated/apps" / svc / "storage.yaml"
    return f.is_file() and any(d and d["metadata"]["name"] == name for d in yaml.safe_load_all(f.read_text()))


def scale(svc: str, replicas: int) -> None:
    sel = f"homeserver/service={svc}"
    kubectl("scale", "deployment", "-n", NAMESPACE, "-l", sel, f"--replicas={replicas}", check=False)
    if replicas == 0:
        # Wait for the Deployments' pods only (DaemonSets can't scale to 0).
        names = subprocess.run(["kubectl", "--context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "-n", NAMESPACE, "get",
                                "deployment", "-l", sel, "-o", "jsonpath={.items[*].metadata.name}"],
                               capture_output=True, text=True).stdout.split()
        for name in names:
            kubectl("wait", "--for=delete", "pod", "-n", NAMESPACE, "-l", f"app.kubernetes.io/name={name}",
                    "--timeout=180s", check=False)


def cmd_import(a) -> None:
    """Copy a Compose snapshot into the test cluster: never the live
    service_data folders, so Docker's data is only ever read. --live-db takes
    own Postgres databases from the running Compose container instead
    (pg_dump, read-only), for when the newest snapshot is older than the data."""
    global LIVE_DB
    LIVE_DB = a.live_db
    for svc in services(a.services):
        snap = snapshot_dir(svc, a.snapshot)
        print(f"== {svc}: " + (f"snapshot {snap.name}" if snap else "no snapshot (homeserver.py takes one on every 'down'); copy_from folders only"))
        data_tar = next(snap.glob("service_data_*.tar.gz"), None) if snap else None
        scale(svc, 0)
        if data_tar and has_pvc(svc, f"{svc}-data"):
            unpack(data_tar, pvc_host_path(f"{svc}-data"))
        elif data_tar:
            # No DATA_ROOT mount in Compose (e.g. guacamole keeps everything
            # in its database); the snapshot's tar should be empty.
            files = [n for n in subprocess.run(["tar", "tzf", str(data_tar)], capture_output=True, text=True).stdout.split()
                     if not n.endswith("/")]
            if files:
                print(f"note: {svc} has no data volume; skipped {len(files)} file(s) in {data_tar.name}", flush=True)
        # Host folders Compose keeps outside DATA_ROOT (copy_from overrides).
        for co in (load_overrides(svc).get("containers") or {}).values():
            for mo in (co.get("mounts") or {}).values():
                if mo.get("volume") and mo.get("copy_from"):
                    copy_folder(Path(host_path(svc, mo["copy_from"])), pvc_host_path(f"{svc}-{slug(mo['volume'])}"))
        for vol_tar in sorted(snap.glob(f"{svc}_*.tar.gz")) if snap else []:
            import_volume(svc, vol_tar)
        scale(svc, 1)
        # DaemonSets can't scale to 0: restart them to pick up the restored files.
        kubectl("rollout", "restart", "daemonset", "-n", NAMESPACE, "-l", f"homeserver/service={svc}", check=False)


LIVE_DB = False


def as_root(mounts: list[str], script: str) -> None:
    """Run a shell script as root in a throwaway container (no network), so
    copies keep every file's owner (postgres 999, clickhouse 101, ...)."""
    args = ["docker", "run", "--rm", "--network", "none"]
    for m in mounts:
        args += ["-v", m]
    run(args + [VERSIONS["WAIT_IMAGE"], "sh", "-c", script])


def unpack(tar: Path, dest: Path) -> None:
    """Replace a volume folder's contents with a snapshot tar's."""
    as_root([f"{tar}:/in.tgz:ro", f"{dest}:/dst"],
            "find /dst -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar xzf /in.tgz -C /dst")


def copy_folder(src: Path, dest: Path) -> None:
    """Copy a host folder into a volume folder (owners and times kept)."""
    if not src.is_dir():
        sys.exit(f"copy_from source {src} is not a folder")
    print(f"+ copy {src} -> {dest}", flush=True)
    as_root([f"{src}:/src:ro", f"{dest}:/dst"],
            "find /dst -mindepth 1 -maxdepth 1 -exec rm -rf {} + && cp -a /src/. /dst/")


def restore_pg(cname: str, db: str, user: str, dump: Path) -> None:
    """Load a pg_dump into the CNPG cluster: recreate the database owned by
    the app's role, create the dump's extensions as superuser (an app role
    may not), then restore everything else as the app's role
    (pg_restore -L with the EXTENSION entries left out)."""
    pod = f"{cname}-1"  # CNPG names the first instance <cluster>-1
    kubectl("wait", "-n", NAMESPACE, "--for=condition=Ready", f"cluster/{cname}", "--timeout=300s")
    ctx = ["kubectl", "--context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "-n", NAMESPACE, "exec", "-i", pod, "-c", "postgres", "--"]
    toc = subprocess.run(ctx + ["sh", "-c", "cat > /controller/restore.dump && pg_restore -l /controller/restore.dump"],
                         stdin=dump.open("rb"), capture_output=True, check=True).stdout.decode()
    # TOC lines look like "4185; 3079 16384 EXTENSION - vchord" (+ owner, if any)
    exts = sorted({m.group(1) for ln in toc.splitlines() if not ln.startswith(";")
                   for m in [re.search(r" EXTENSION - (\S+)", ln)] if m})
    keep = "\n".join(ln for ln in toc.splitlines() if " EXTENSION - " not in ln and " COMMENT - EXTENSION " not in ln)
    sql = (f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE);\nCREATE DATABASE "{db}" OWNER "{user}";\n')
    subprocess.run(ctx + ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres"], input=sql.encode(), check=True)
    if exts:
        subprocess.run(ctx + ["psql", "-v", "ON_ERROR_STOP=1", "-d", db], check=True,
                       input="".join(f'CREATE EXTENSION IF NOT EXISTS "{e}" CASCADE;\n' for e in exts).encode())
    print(f"+ pg_restore into {pod} ({db}, owned by {user}; extensions: {', '.join(exts) or 'none'})", flush=True)
    subprocess.run(ctx + ["sh", "-c", f"cat > /controller/restore.list && pg_restore --no-owner --role={user} "
                                      f"-L /controller/restore.list -d {db} /controller/restore.dump; "
                                      "rc=$?; rm -f /controller/restore.dump /controller/restore.list; exit $rc"],
                   input=keep.encode(), check=False)


def import_mariadb(svc: str, owner: tuple, vol: str, vol_tar: Path, mdb: dict) -> None:
    """Own MariaDB volume -> mariadb-dump -> the operator's MariaDB: from a
    throwaway container of the Compose image on the unpacked snapshot, or
    (--live-db) from the running Compose container."""
    n, s = owner
    cname = s.get("container_name") or n
    env = load_env(REPO / "services" / svc / ".env")
    root_pw = env.get(mdb["spec"]["rootPasswordSecretKeyRef"]["key"], "")
    db = mdb["spec"]["database"]
    with tempfile.TemporaryDirectory(prefix=f"k8s-import-{svc}-") as tmp:
        dump = Path(tmp) / "db.sql"
        src = cname
        if not LIVE_DB:
            data = Path(tmp) / "data"
            data.mkdir()
            run(["tar", "xzf", str(vol_tar), "-C", str(data), "--no-same-owner"])
            src = f"k8s-import-{svc}"
            mount = next(m["target"] for m in s["volumes"] if str(m.get("source")) == vol)
            run(["docker", "run", "-d", "--rm", "--name", src, "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
                 "-v", f"{data}:{mount}", s["image"]])
        try:
            for _ in range(60):
                if subprocess.run(["docker", "exec", "-e", f"MYSQL_PWD={root_pw}", src, "mariadb-admin", "-uroot", "ping"],
                                  capture_output=True).returncode == 0:
                    break
                time.sleep(2)
            else:
                sys.exit(f"{svc}: MariaDB source {src} didn't answer")
            print(f"+ mariadb-dump {db} from {src}" + (" (running Compose container, read-only)" if LIVE_DB else ""), flush=True)
            with dump.open("wb") as f:
                subprocess.run(["docker", "exec", "-e", f"MYSQL_PWD={root_pw}", src, "mariadb-dump", "-uroot",
                                "--single-transaction", "--routines", "--triggers", db], stdout=f, check=True)
        finally:
            if not LIVE_DB:
                subprocess.run(["docker", "stop", src], capture_output=True)
        kubectl("wait", "-n", NAMESPACE, "--for=condition=Ready", f"mariadb/{cname}", "--timeout=300s")
        print(f"+ load into {cname}-0 ({db})", flush=True)
        with dump.open("rb") as f:
            subprocess.run(["kubectl", "--context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "-n", NAMESPACE, "exec", "-i",
                            f"{cname}-0", "--", "sh", "-c", f'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" {db}'],
                           stdin=f, check=True)


def import_volume(svc: str, vol_tar: Path) -> None:
    """A named-volume tar from the snapshot. An own Postgres volume is loaded
    with pg_dump/pg_restore (CNPG can't adopt a raw data folder): the tar is
    unpacked into scratch space, served by a throwaway container of the
    Compose image (no network), dumped, and restored into the CNPG cluster.
    Any other named volume is unpacked into its PVC."""
    compose = load_compose(svc)
    vol = vol_tar.name[len(svc) + 1:].rsplit("_", 1)[0].removeprefix(f"{svc}_")
    owner = next(((n, s) for n, s in compose["services"].items()
                  if any(str(m.get("source")) == vol for m in s.get("volumes") or [])), None)
    if owner and own_postgres(svc, owner[0], owner[1], load_overrides(svc)):
        n, s = owner
        cname = s.get("container_name") or n
        env = load_env(REPO / "services" / svc / ".env")
        own = own_db_keys(svc)
        db = own["db"]
        user = env.get(own["user_key"], own["user"]) if own["user_key"] else own["user"]
        with tempfile.TemporaryDirectory(prefix=f"k8s-import-{svc}-") as tmp:
            dump = Path(tmp) / "db.dump"
            if LIVE_DB:
                # pg_dump reads one consistent snapshot of the running
                # database without blocking it (PostgreSQL docs, "SQL Dump"):
                # read-only for Compose, which keeps running.
                print(f"+ pg_dump from the running {cname} (read-only)", flush=True)
                with dump.open("wb") as f:
                    subprocess.run(["docker", "exec", cname, "pg_dump", "-Fc", "-U", user, "-d", db], stdout=f, check=True)
                restore_pg(cname, db, user, dump)
                return
            pgdata = Path(tmp) / "pg"
            pgdata.mkdir()
            run(["tar", "xzf", str(vol_tar), "-C", str(pgdata), "--no-same-owner"])
            name = f"k8s-import-{svc}"
            mount = next(m["target"] for m in s["volumes"] if str(m.get("source")) == vol)
            run(["docker", "run", "-d", "--rm", "--name", name, "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
                 "-v", f"{pgdata}:{mount}", s["image"]])
            try:
                for _ in range(60):
                    if subprocess.run(["docker", "exec", name, "pg_isready", "-U", user, "-d", db],
                                      capture_output=True).returncode == 0:
                        break
                    time.sleep(2)
                else:
                    sys.exit(f"{svc}: the throwaway Postgres didn't start; see `docker logs {name}`")
                with dump.open("wb") as f:
                    subprocess.run(["docker", "exec", name, "pg_dump", "-Fc", "-U", user, "-d", db], stdout=f, check=True)
            finally:
                subprocess.run(["docker", "stop", name], capture_output=True)
            restore_pg(cname, db, user, dump)
        return
    if owner and (mdb := own_mariadb(svc, owner[0], owner[1], {})):
        import_mariadb(svc, owner, vol, vol_tar, mdb)
        return
    unpack(vol_tar, pvc_host_path(f"{svc}-{slug(vol)}"))


def cmd_validate(a) -> None:
    """Server-side dry run of each service's manifests: the API server checks
    schemas, operator CRDs and field values without creating anything."""
    bad = []
    names = services(a.services)
    for svc in names:
        d = K8S / "generated/envs" / a.env / svc
        if not d.is_dir():
            continue
        p = subprocess.run(["kubectl", "--context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "apply", "--dry-run=server",
                            "-k", str(d)], capture_output=True, text=True)
        if p.returncode != 0:
            bad.append(svc)
            print(f"FAIL {svc}: " + " | ".join(l for l in p.stderr.splitlines() if l.strip() and not l.startswith("Warning"))[:400])
    print(f"{len(names) - len(bad)}/{len(names)} pass the server-side dry run")
    if bad:
        sys.exit(1)


def cmd_status(_a) -> None:
    kubectl("get", "pods,svc,pvc,httproute", "-n", NAMESPACE, "-o", "wide", check=False)


def cmd_delete(_a) -> None:
    run(["kind", "delete", "cluster", "--name", cfg()["K8S_CLUSTER_NAME"]])
    print("Host data folders (K8S_FAST_PATH/K8S_BULK_PATH/K8S_IMAGES_PATH) are kept; delete them by hand if wanted.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["create", "install", "secrets", "apply", "import", "validate", "status", "delete"])
    ap.add_argument("services", nargs="*")
    ap.add_argument("--env", default="test", choices=["test", "prod"])
    ap.add_argument("--snapshot", help="import: a snapshot folder name (default: the newest)")
    ap.add_argument("--live-db", action="store_true", help="import: own Postgres from the running Compose container (pg_dump)")
    a = ap.parse_args()
    {"create": cmd_create, "install": cmd_install, "secrets": cmd_secrets, "apply": cmd_apply, "import": cmd_import, "validate": cmd_validate,
     "status": cmd_status, "delete": cmd_delete}[a.action](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
