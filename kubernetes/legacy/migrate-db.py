#!/usr/bin/env python3
"""kubernetes/migrate-db.py — copies each service's database out of its
already-running Compose container and into this pilot's k8s cluster (its
dedicated StatefulSet, or the shared Postgres/MariaDB server it was
onboarded onto) — so the accounts, password hashes, and app state that
already exist in Compose show up in k8s too. This is the piece "login
stuff works perfectly fine after migrating" actually depends on: user
tables live in the database, not in a bind-mounted config file.

Run this AFTER `uv run kubernetes/sync-env-from-compose.py` and
`uv run kubernetes/apply-secrets.py`, not before — several apps use their
app-level secret (Firefly's APP_KEY, Documenso's encryption keys,
Outline's SECRET_KEY, NocoDB's JWT secret, ...) to encrypt columns in
their own database. Copying the database across before the two sides
share that secret means the encrypted rows land in k8s undecryptable —
right values, wrong key. See kubernetes/README.md's "Migrating data from
Compose" section for the full recommended order.

Scope: Postgres and MariaDB only — the two engines every dedicated
StatefulSet and both shared servers in this pilot use. RocketChat's
MongoDB replica set is not handled (different tooling entirely — migrate
by hand with `mongodump`/`mongorestore` if you need it). Bind-mounted
files (Nextcloud's uploaded files, Immich's photos, Jellyfin's media,
wiki attachments, ...) under service_data/data/<service>/ are also NOT
copied by this script — those aren't inside any database, and every
service bind-mounts them at a different path, so there is no generic
"copy this into that PVC" that's safe across all of them. This script
only moves what pg_dump/mariadb-dump can see.

Usage:
  uv run kubernetes/migrate-db.py <service> [<service> ...]
  uv run kubernetes/migrate-db.py --all
  uv run kubernetes/migrate-db.py --all --yes
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

K8S_DIR = Path(__file__).resolve().parent
BASE_DIR = K8S_DIR.parent
APPS_DIR = K8S_DIR / "apps"

sys.path.insert(0, str(K8S_DIR))
from k8s import (  # noqa: E402
    RESET,
    BOLD,
    info,
    success,
    error,
    warn,
    header,
    kubectl_run,
    kubectl_json,
    check_context,
    ALL_PORTED,
)


def docker_inspect(container: str) -> dict | None:
    try:
        result = subprocess.run(["docker", "inspect", container], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return data[0] if data else None


def container_env(inspected: dict) -> dict[str, str]:
    env: dict[str, str] = {}
    for entry in inspected.get("Config", {}).get("Env", []):
        key, _, val = entry.partition("=")
        env[key] = val
    return env


def detect_compose_source(service: str) -> dict | None:
    """Compose-side DB container for `service`, following the `<service>-db`
    container-name convention every service in this repo already uses.
    Returns None (not an error — caller reports why) if that container
    doesn't exist or isn't running, or if it isn't Postgres/MariaDB."""
    container = f"{service}-db"
    inspected = docker_inspect(container)
    if inspected is None:
        return None
    if not inspected.get("State", {}).get("Running"):
        return {"engine": "not-running", "container": container}
    image = inspected.get("Config", {}).get("Image", "")
    env = container_env(inspected)
    base_image = image.rsplit("/", 1)[-1]
    if base_image.startswith("postgres:"):
        return {
            "engine": "postgres",
            "container": container,
            "db": env.get("POSTGRES_DB", service),
            "user": env.get("POSTGRES_USER", service),
        }
    if base_image.startswith("mariadb:") or base_image.startswith("mysql:"):
        return {
            "engine": "mariadb",
            "container": container,
            "db": env.get("MYSQL_DATABASE", service),
            "root_password": env.get("MYSQL_ROOT_PASSWORD", ""),
        }
    return {"engine": "unsupported", "container": container, "image": image}


def get_secret_value(name: str, namespace: str, key: str) -> str | None:
    result = kubectl_run(["get", "secret", name, "-n", namespace, "-o", f"jsonpath={{.data.{key}}}"], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    import base64

    try:
        return base64.b64decode(result.stdout.strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def detect_k8s_target(service: str) -> dict | None:
    """Where this service's data should land in the cluster: its own
    dedicated StatefulSet (kubectl get statefulset <service>-db -n apps),
    or the shared Postgres/MariaDB server if it was onboarded onto one
    (kubernetes/apps/<service>/db-init-job.yaml exists on disk — same
    signal kubernetes/README.md's "What's installed" table uses)."""
    db_init = APPS_DIR / service / "db-init-job.yaml"
    if db_init.is_file():
        content = db_init.read_text(encoding="utf-8")
        if "image: postgres" in content:
            return {"engine": "postgres", "namespace": "data", "pod": "postgres-shared-0", "db": service, "user": service}
        if "image: mariadb" in content or "image: mysql" in content:
            root_pw = get_secret_value("mariadb-shared-credentials", "data", "root-password")
            return {"engine": "mariadb", "namespace": "data", "pod": "mariadb-shared-0", "db": service, "root_password": root_pw}
        return None

    sts = kubectl_json(["get", "statefulset", f"{service}-db", "-n", "apps"])
    if sts is None:
        return None
    containers = sts.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    image = containers[0].get("image", "") if containers else ""
    pod = f"{service}-db-0"
    if "postgres" in image:
        return {"engine": "postgres", "namespace": "apps", "pod": pod, "db": service, "user": service}
    if "mariadb" in image or "mysql" in image:
        root_pw = get_secret_value(f"{service}-db-credentials", "apps", "root-password")
        return {"engine": "mariadb", "namespace": "apps", "pod": pod, "db": service, "root_password": root_pw}
    return None


def wait_for_pod_ready(namespace: str, pod: str, timeout: str = "120s") -> bool:
    result = kubectl_run(["wait", "--for=condition=ready", f"pod/{pod}", "-n", namespace, f"--timeout={timeout}"], check=False)
    return result.returncode == 0


def run_pipe(dump_cmd: list[str], restore_cmd: list[str]) -> tuple[bool, str]:
    """docker exec ... pg_dump/mariadb-dump | kubectl exec -i ... psql/mariadb
    — streamed directly, never buffered fully in Python, never through a
    shell (list-form args on both ends, same convention as every other
    script in this directory)."""
    dumper = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    restorer = subprocess.Popen(restore_cmd, stdin=dumper.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if dumper.stdout is not None:
        dumper.stdout.close()
    restore_out, restore_err = restorer.communicate()
    _, dump_err = dumper.communicate()
    if dumper.returncode != 0:
        return False, f"dump failed: {dump_err.decode(errors='replace').strip()}"
    if restorer.returncode != 0:
        return False, f"restore failed: {restore_err.decode(errors='replace').strip()}"
    return True, ""


def migrate_service(service: str) -> tuple[bool, str]:
    source = detect_compose_source(service)
    if source is None:
        return False, f"no {service}-db Compose container found — nothing to migrate from"
    if source["engine"] == "not-running":
        return False, f"{service}-db exists but isn't running — start it (uv run homeserver.py dev up {service}) first"
    if source["engine"] == "unsupported":
        return False, f"{service}-db runs an unsupported image ({source['image']}) — Postgres/MariaDB only"

    target = detect_k8s_target(service)
    if target is None:
        return False, f"no k8s DB found for '{service}' — not onboarded onto a dedicated StatefulSet or the shared server yet"
    if source["engine"] != target["engine"]:
        return False, f"engine mismatch — Compose runs {source['engine']}, k8s target is {target['engine']}"

    if not wait_for_pod_ready(target["namespace"], target["pod"]):
        return False, f"target pod {target['pod']} in namespace {target['namespace']} never became ready — is it scaled up? (uv run kubernetes/k8s.py up {service})"

    if source["engine"] == "postgres":
        dump_cmd = ["docker", "exec", source["container"], "pg_dump", "-U", source["user"], "--no-owner", "--no-privileges", source["db"]]
        restore_cmd = [
            "kubectl", "exec", "-i", "-n", target["namespace"], target["pod"], "--",
            "psql", "-U", target["user"], "-d", target["db"], "-v", "ON_ERROR_STOP=1",
        ]
        return run_pipe(dump_cmd, restore_cmd)

    # mariadb
    if not source.get("root_password"):
        return False, "Compose side has no MYSQL_ROOT_PASSWORD set — can't authenticate to dump"
    if not target.get("root_password"):
        return False, "k8s side has no root-password Secret yet — run apply-secrets.py first"
    dump_cmd = [
        "docker", "exec", "-e", f"MYSQL_PWD={source['root_password']}", source["container"],
        "mariadb-dump", "-u", "root", "--skip-add-locks", source["db"],
    ]
    restore_cmd = [
        "kubectl", "exec", "-i", "-n", target["namespace"], target["pod"], "--",
        "env", f"MYSQL_PWD={target['root_password']}", "mariadb", "-u", "root", target["db"],
    ]
    return run_pipe(dump_cmd, restore_cmd)


def main() -> int:
    args = sys.argv[1:]
    assume_yes = "--yes" in args
    args = [a for a in args if a != "--yes"]

    if not args:
        error("usage: uv run kubernetes/migrate-db.py <service> [<service> ...] | --all [--yes]")
        return 1

    if args == ["--all"]:
        targets = sorted(ALL_PORTED)
    else:
        targets = [a for a in args if a != "--all"]
        for t in targets:
            if not (APPS_DIR / t).is_dir():
                error(f"unknown service '{t}' — no kubernetes/apps/{t}/ directory")
                return 1

    header("kubernetes/migrate-db.py — copying databases from Compose into k8s")
    if not check_context(dry_run=False):
        return 1

    if not assume_yes and sys.stdin.isatty():
        print(f"\n{BOLD}This will overwrite data in {len(targets)} k8s database(s) with Compose's current data:{RESET}")
        print(f"  {' '.join(targets)}")
        try:
            reply = input(f"\n{BOLD}Continue? [y/N]{RESET} ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return 1
        if reply not in ("y", "yes"):
            info("Cancelled")
            return 1

    migrated, skipped, failed = [], [], []
    for service in targets:
        ok, detail = migrate_service(service)
        if ok:
            success(f"{service}: migrated")
            migrated.append(service)
        elif detail.startswith(("no ", "engine mismatch")):
            warn(f"{service}: skipped — {detail}")
            skipped.append(service)
        else:
            error(f"{service}: {detail}")
            failed.append(service)

    header("Done")
    info(f"{len(migrated)} migrated, {len(skipped)} skipped (no matching DB on one side), {len(failed)} failed")
    if failed:
        error(f"failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
