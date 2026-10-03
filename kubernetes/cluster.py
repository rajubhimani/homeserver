#!/usr/bin/env python3
"""Create and drive the kind test cluster that runs the generated manifests.

    uv run kubernetes/cluster.py create            # kind cluster from cluster/kind-config.template.yaml + kubernetes/.env
    uv run kubernetes/cluster.py install           # Gateway API, namespaces, Traefik, storage classes, DB operators
    uv run kubernetes/cluster.py secrets [svc...]  # services/<svc>/.env -> Secret <svc>-env; root .env -> ConfigMap
    uv run kubernetes/cluster.py apply   [svc...]  # kubectl apply -k kubernetes/generated/envs/<env>/<svc>
    uv run kubernetes/cluster.py import  <svc...> [--snapshot TS]  # copy a Compose snapshot's data into the cluster
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
from generate import load_compose, load_env, load_scope, own_db_keys, own_postgres, shared_db_apps, slug  # noqa: E402

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
    # kind's local-path provisioner: allow the fast/bulk folders, then the classes.
    conf = {"nodePathMap": [{"node": "DEFAULT_PATH_FOR_NON_LISTED_NODES",
                             "paths": ["/var/local-path-provisioner", "/var/k8s/fast", "/var/k8s/bulk"]}]}
    kubectl("-n", "local-path-storage", "patch", "configmap", "local-path-config", "--type", "merge",
            "-p", json.dumps({"data": {"config.json": json.dumps(conf, indent=1)}}))
    kubectl("apply", "-f", str(K8S / "cluster/storage.yaml"))
    kubectl("apply", "-f", str(K8S / "cluster/traefik/nginx-plain-alias.yaml"))
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
            kubectl("apply", "-f", "-", input=basic_auth(f"{svc}-db-owner", env.get(own[0], ""), env.get(own[1], "")))
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


def snapshot_dir(svc: str, ts: str | None) -> Path:
    """The service's newest regular Compose snapshot (timestamp-named folders
    only, as homeserver.py's restore picks them), or the one asked for."""
    root = REPO / "service_data/backup" / svc
    snaps = sorted(d.name for d in root.glob("*") if d.is_dir() and d.name[:8].isdigit()) if root.is_dir() else []
    if ts:
        if ts not in snaps and not (root / ts).is_dir():
            sys.exit(f"{svc}: no snapshot {ts} in {root}")
        return root / ts
    if not snaps:
        sys.exit(f"{svc}: no snapshot in {root} (homeserver.py takes one on every 'down')")
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
        print(f"== {svc}: snapshot {snap.name}")
        data_tar = next(snap.glob("service_data_*.tar.gz"), None)
        scale(svc, 0)
        if data_tar:
            dest = pvc_host_path(f"{svc}-data")
            # Replace the folder's contents with the snapshot's.
            for child in dest.iterdir():
                run(["rm", "-rf", str(child)])
            run(["tar", "xzf", str(data_tar), "-C", str(dest), "--no-same-owner", "--no-overwrite-dir"])
        for vol_tar in sorted(snap.glob(f"{svc}_*.tar.gz")):
            import_volume(svc, vol_tar)
        scale(svc, 1)
        # DaemonSets can't scale to 0: restart them to pick up the restored files.
        kubectl("rollout", "restart", "daemonset", "-n", NAMESPACE, "-l", f"homeserver/service={svc}", check=False)


LIVE_DB = False


def restore_pg(cname: str, db: str, user: str, dump: Path) -> None:
    pod = f"{cname}-1"  # CNPG names the first instance <cluster>-1
    kubectl("wait", "-n", NAMESPACE, "--for=condition=Ready", f"cluster/{cname}", "--timeout=300s")
    print(f"+ pg_restore into {pod} ({db}, owned by {user})", flush=True)
    with dump.open("rb") as f:
        subprocess.run(["kubectl", "--context", f"kind-{cfg()['K8S_CLUSTER_NAME']}", "-n", NAMESPACE, "exec", "-i",
                        pod, "-c", "postgres", "--", "pg_restore", "--clean", "--if-exists", "--no-owner",
                        f"--role={user}", "-d", db], stdin=f, check=False)


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
    if owner and own_postgres(svc, owner[0], owner[1], {}):
        n, s = owner
        cname = s.get("container_name") or n
        env = load_env(REPO / "services" / svc / ".env")
        user_key, _ = own_db_keys(svc)
        db = env.get("POSTGRES_DB", "")
        user = env.get(user_key, "")
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
    dest = pvc_host_path(f"{svc}-{slug(vol)}")
    for child in dest.iterdir():
        run(["rm", "-rf", str(child)])
    run(["tar", "xzf", str(vol_tar), "-C", str(dest), "--no-same-owner", "--no-overwrite-dir"])


def cmd_status(_a) -> None:
    kubectl("get", "pods,svc,pvc,httproute", "-n", NAMESPACE, "-o", "wide", check=False)


def cmd_delete(_a) -> None:
    run(["kind", "delete", "cluster", "--name", cfg()["K8S_CLUSTER_NAME"]])
    print("Host data folders (K8S_FAST_PATH/K8S_BULK_PATH/K8S_IMAGES_PATH) are kept; delete them by hand if wanted.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["create", "install", "secrets", "apply", "import", "status", "delete"])
    ap.add_argument("services", nargs="*")
    ap.add_argument("--env", default="test", choices=["test", "prod"])
    ap.add_argument("--snapshot", help="import: a snapshot folder name (default: the newest)")
    ap.add_argument("--live-db", action="store_true", help="import: own Postgres from the running Compose container (pg_dump)")
    a = ap.parse_args()
    {"create": cmd_create, "install": cmd_install, "secrets": cmd_secrets, "apply": cmd_apply, "import": cmd_import,
     "status": cmd_status, "delete": cmd_delete}[a.action](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
