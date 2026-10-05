"""Every app on a shared database server must connect to the database, user
and password that homeserver.py provisions for it (services.json "shared_db"),
on the right host. Compose files are rendered the way docker compose does
(${VAR}, ${VAR:-default}, $$) from each service's .env.example, so a renamed
key, a stale <svc>-db host or a hard-coded database name fails here instead of
at first start."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest
import yaml

import homeserver as hs

REPO = hs.BASE_DIR
SHARED_USERS = [s for s in hs._SERVICES_DATA["services"] if s.get("shared_db")]

# Apps whose connection isn't in compose env at all — and where it is instead.
CONNECTION_ELSEWHERE = {
    "dagster": "services/dagster/webserver-daemon/dagster.yaml",  # checked below
    "orangehrm": "docs/services/orangehrm.md",  # entered in its web installer
}


def render(svc: str) -> dict:
    env = hs.load_env_file(REPO / "services" / svc / ".env.example")
    env.update({"DOMAIN": "example.test", "DATA_ROOT": "/data", "DOCKER_SOCKET": "/var/run/docker.sock"})

    def interp(text: str) -> str:
        text = re.sub(r"\$\{(\w+)(?::?-([^}]*))?\}", lambda m: env.get(m.group(1)) or (m.group(2) or ""), text)
        return text.replace("$$", "$")

    merged: dict = {}
    for name in (hs.base_file(svc), "compose.prod.yml"):
        doc = yaml.safe_load(interp((REPO / "services" / svc / name).read_text())) or {}
        for sname, sdef in (doc.get("services") or {}).items():
            merged.setdefault(sname, {}).update(sdef or {})
    for sdef in merged.values():
        e = sdef.get("environment") or {}
        if isinstance(e, list):
            e = dict(x.split("=", 1) for x in e)
        # Like compose: env_file values first, `environment:` overrides them.
        files = sdef.get("env_file") or []
        base = dict(env) if (files == ".env" or ".env" in files) else {}
        base.update({k: "" if v is None else str(v) for k, v in e.items()})
        sdef["environment"] = base
        sdef["_explicit"] = set(e)  # keys the service sets itself, not just via env_file
    return merged


def creds(svc: str) -> dict:
    spec = hs._SERVICES_BY_SLUG[svc]["shared_db"]
    env = hs.load_env_file(REPO / "services" / svc / ".env.example")
    val = lambda k: k[1:] if k.startswith("=") else env.get(k, "")  # noqa: E731
    return {"host": hs.SHARED_DB_SERVICES[spec["engine"]], "db": val(spec["db"]), "user": val(spec["user"]),
            "password": val(spec["password"]), "extra": spec.get("extra_dbs", [])}


def check_url(url: str, c: dict) -> list[str]:
    p = urlparse(url.replace("pg://", "postgres://"))
    q = parse_qs(p.query)
    user = unquote(p.username) if p.username else (q.get("u") or [None])[0]
    password = unquote(p.password) if p.password else (q.get("p") or [None])[0]
    db = p.path.lstrip("/") or (q.get("d") or [None])[0]
    problems = []
    if p.hostname != c["host"]:
        problems.append(f"host {p.hostname!r} != {c['host']!r}")
    if db != c["db"]:
        problems.append(f"database {db!r} != {c['db']!r}")
    if user is not None and user != c["user"]:
        problems.append(f"user {user!r} != {c['user']!r}")
    if password is not None and password != c["password"]:
        problems.append("password doesn't come from the shared_db password key")
    return problems


@pytest.mark.parametrize("entry", SHARED_USERS, ids=lambda s: s["slug"])
def test_app_connects_to_its_own_provisioned_database(entry):
    svc = entry["slug"]
    c = creds(svc)
    services = render(svc)
    problems, connections = [], 0
    old_host = re.compile(rf"(?<![\w-]){re.escape(svc)}-db(?![\w-])")
    for name, sdef in services.items():
        env = sdef["environment"]
        for key, value in env.items():
            if old_host.search(value):
                problems.append(f"{name}.{key} still points at the removed {svc}-db container")
            # Every database URL, whatever host it names (a stale one included).
            for url in re.findall(r"(?:postgres(?:ql)?(?:\+\w+)?|pg|mysql|mariadb)://\S+", value):
                connections += 1
                problems += [f"{name}.{key}: {p}" for p in check_url(url, c)]
            m = re.search(r"Host=([^;]+);(?:Port=[^;]+;)?Database=([^;]+);Username=([^;]+);Password=([^;]+)", value)
            if m:
                connections += 1
                got = dict(zip(("host", "db", "user", "password"), m.groups()))
                problems += [f"{name}.{key}: {k} {got[k]!r} mismatch" for k in got if got[k] != c[k]]
        # Separate host/database/user/password variables: match by role, so a
        # database and user that share a name can't satisfy each other.
        # DB_HOST is the stack's own convention variable (every shared_db app's
        # .env; see test_external_db.py). Arriving only via env_file it's not
        # an app setting, so it's skipped unless the service sets it itself
        # (bookstack/invoiceshelf, whose apps read DB_HOST natively).
        host_keys = [k for k, v in env.items() if v == c["host"] and (k != "DB_HOST" or k in sdef["_explicit"])]
        if host_keys:
            connections += 1
            # Variables that belong to this connection share the host
            # variable's prefix: PAPERLESS_DB{HOST,NAME,USER,PASS},
            # SYMFONY__ENV__DATABASE_{HOST,NAME,USER,PASSWORD}, POSTGRES_{SERVER,DB,...}.
            prefix = re.sub(r"(HOST|SERVER|SEEDS)$", "", host_keys[0], flags=re.I)
            role_of = {
                "db": re.compile(r"^(DB|DATABASE|NAME|DBNAME)$", re.I),
                "user": re.compile(r"^(USER|USERNAME)$", re.I),
                "password": re.compile(r"^(PASSWORD|PWD|PASS)$", re.I),
            }
            for role, pat in role_of.items():
                cands = {k: v for k, v in env.items() if k.startswith(prefix) and pat.match(k[len(prefix):])}
                if not cands and not (svc == "temporal" and role == "db"):  # temporal: DBNAME, checked below
                    problems.append(f"{name}: {host_keys[0]}={c['host']} but no {prefix}<{role}> variable next to it")
                for k, v in cands.items():
                    if v != c[role]:
                        shown = "***" if role == "password" else repr(v)
                        problems.append(f"{name}.{k} = {shown}, expected the provisioned {role}")
        if svc == "temporal" and name == "temporal":
            if env.get("DBNAME") != c["db"]:
                problems.append(f"temporal.DBNAME {env.get('DBNAME')!r} != provisioned {c['db']!r}")
            if env.get("VISIBILITY_DBNAME") not in c["extra"]:
                problems.append(f"temporal.VISIBILITY_DBNAME {env.get('VISIBILITY_DBNAME')!r} not in extra_dbs {c['extra']}")
    if svc in CONNECTION_ELSEWHERE:
        # The host itself comes from DB_HOST in .env (default: the shared server).
        where = (REPO / CONNECTION_ELSEWHERE[svc]).read_text()
        assert c["host"] in where or "env: DB_HOST" in where
    else:
        assert connections, f"no container in {svc} points at {c['host']}"
    assert not problems, "\n".join(problems)


def test_temporal_schema_setup_targets_both_provisioned_databases():
    c = creds("temporal")
    cmd = " ".join(render("temporal")["temporal-schema-setup"]["command"])
    assert f"--ep {c['host']}" in cmd and f"-u {c['user']}" in cmd
    for db in [c["db"], *c["extra"]]:
        assert f"--db {db} update-schema" in cmd, f"schema setup never updates {db}"
    assert not re.search(r"\bcreate\b", cmd), "temporal's role can't CREATE DATABASE; provisioning creates both databases"


def test_dagster_yaml_storage_uses_shared_postgres_and_spec_keys():
    spec = hs._SERVICES_BY_SLUG["dagster"]["shared_db"]
    cfg = yaml.safe_load((REPO / CONNECTION_ELSEWHERE["dagster"]).read_text())
    blocks = [v["config"]["postgres_db"] for k, v in cfg.items() if isinstance(v, dict) and "postgres_db" in (v.get("config") or {})]
    assert len(blocks) == 3, "run, event log and schedule storage should all be Postgres"
    for b in blocks:
        assert b["hostname"] == {"env": "DB_HOST"} and b["port"] == {"env": "DB_PORT"}
        assert (b["db_name"]["env"], b["username"]["env"], b["password"]["env"]) == (spec["db"], spec["user"], spec["password"])
    assert set(cfg["run_launcher"]["config"]["env_vars"]) >= {spec["db"], spec["user"], spec["password"], "DB_HOST", "DB_PORT"}
    assert "DB_HOST=shared-postgres" in (REPO / "services/dagster/.env.example").read_text()


# ── credential isolation ──────────────────────────────────────────

ADMIN_KEYS = {"MARIADB_ROOT_PASSWORD", "MYSQL_ROOT_PASSWORD"}


@pytest.mark.parametrize("entry", SHARED_USERS, ids=lambda s: s["slug"])
def test_app_never_gets_admin_credentials(entry):
    """An app on a shared server logs in as its own role/user only. It must
    not carry an admin/root password (its env_file is injected into its
    containers) or be configured as the server's admin user."""
    svc = entry["slug"]
    keys = set(hs.load_env_file(REPO / "services" / svc / ".env.example"))
    assert not keys & ADMIN_KEYS, f"{svc}/.env.example still has {keys & ADMIN_KEYS}"
    admin_user = "postgres" if entry["shared_db"]["engine"] == "postgres" else "root"
    assert creds(svc)["user"] != admin_user, f"{svc} would log in as the shared server's admin"
    for name, sdef in render(svc).items():
        assert not set(sdef["environment"]) & ADMIN_KEYS, f"{name} gets an admin password variable"


def test_admin_passwords_live_only_in_the_shared_server_services():
    for server in hs.SHARED_DB_SERVICES.values():
        compose = (REPO / "services" / server / "compose.yml").read_text()
        assert "env_file: .env" in compose
    for entry in SHARED_USERS:
        for f in (REPO / "services" / entry["slug"]).glob("*compose*.yml"):
            text = "\n".join(l for l in f.read_text().splitlines() if not l.lstrip().startswith("#"))
            for server in hs.SHARED_DB_SERVICES.values():
                assert f"services/{server}" not in text and f"../{server}/" not in text, \
                    f"{f} reads the shared server's own files (admin password)"
