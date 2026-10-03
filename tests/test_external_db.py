"""An app's database can live outside the stack: DB_HOST in its .env pointing
at a managed database (RDS, Azure Flexible Server, Cloud SQL...) instead of
shared-postgres/shared-mariadb. homeserver.py must then leave it alone: no
shared server started, provisioned, dumped, restored or dropped for that app,
and never counted as a user of the shared server. See docs/10-new-services.md
"Managed-cloud parity" and docs/services/shared-postgres.md."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import homeserver as hs
from conftest import shared_db_users

REPO = hs.BASE_DIR
EXTERNAL = "mydb.abc123.eu-west-1.rds.amazonaws.com"


@pytest.fixture
def external(fake, monkeypatch):
    """One Postgres shared-db app whose DB_HOST points outside the stack."""
    svc = shared_db_users("postgres")[0]
    real_load = hs.load_env_file

    def load(path):
        vals = dict(real_load(path))
        if Path(path).parent.name == svc and Path(path).name == ".env":
            vals["DB_HOST"] = EXTERNAL
        return vals

    monkeypatch.setattr(hs, "load_env_file", load)
    return svc


def test_default_db_host_is_the_shared_server(fake):
    for svc in shared_db_users("postgres") + shared_db_users("mariadb"):
        assert hs.shared_db_external(svc) is None, f"{svc}: .env.example must default DB_HOST to the shared server"
        assert hs.shared_db_creds(svc), svc


def test_external_host_disables_shared_management(external):
    assert hs.shared_db_external(external) == EXTERNAL
    assert hs.shared_db_creds(external) is None


def test_up_with_external_db_never_starts_the_shared_server(fake, cli, external):
    cli("prod", "up", external)
    started = [e[1] for e in fake.events if e[0] == "up"]
    assert external in started
    assert hs.SHARED_DB_SERVICES["postgres"] not in started
    assert not [e for e in fake.events if e[0] == "create_db"], "nothing may be provisioned for an outside database"


def test_backup_and_reset_never_dump_or_drop_an_external_db(fake, cli, external):
    fake.volumes.add(f"{external}_data")
    cli("prod", "backup", external)
    cli("prod", "reset", external, "-y")
    kinds = {e[0] for e in fake.events}
    assert not kinds & {"pg_dump", "drop_db", "create_db"}


def test_dump_refuses_an_external_db(fake, external):
    assert hs.do_dump(external, "prod", None) is False


def test_shared_db_apps_never_hardcode_the_shared_host():
    """Every shared_db app reaches its database through ${DB_HOST}/${DB_PORT},
    so moving it to a managed database is a .env change only."""
    data = json.loads((REPO / "services.json").read_text())
    offenders = []
    for s in data["services"]:
        sd = s.get("shared_db")
        if not sd:
            continue
        host = hs.SHARED_DB_SERVICES[sd["engine"]]
        d = REPO / "services" / s["slug"]
        for f in [d / "compose.yml", *d.rglob("*.yaml")]:
            if not f.is_file():
                continue
            for n, line in enumerate(f.read_text().splitlines(), 1):
                if host in line and not line.lstrip().startswith("#"):
                    offenders.append(f"{f.relative_to(REPO)}:{n}: {line.strip()}")
        ex = (d / ".env.example").read_text()
        assert re.search(rf"^DB_HOST={re.escape(host)}$", ex, re.M), f"{s['slug']}/.env.example: DB_HOST={host}"
    assert not offenders, "use ${DB_HOST}/${DB_PORT}:\n" + "\n".join(offenders)


BACKING_IMAGE = re.compile(r"(postgres|pgvector|mariadb|mysql|valkey|redis|rabbitmq|memcached|minio|mongo|clickhouse)", re.I)
# Containers that set up their own project's backing service (bucket/replica-set
# init) legitimately name it; Supabase is a tested upstream set whose managed
# equivalent is Supabase Cloud, not a generic database.
SETUP_IMAGES = re.compile(r"(minio/mc|pgsty/mc|mongodb-community-server|admin-tools)", re.I)
SKIP_SERVICES = {"supabase"}


def _backing_names(doc: dict) -> set[str]:
    names = set()
    for name, s in (doc.get("services") or {}).items():
        s = s or {}
        if BACKING_IMAGE.search(str(s.get("image", ""))) and not SETUP_IMAGES.search(str(s.get("image", ""))):
            names |= {name, s.get("container_name", name)}
    return names


@pytest.mark.parametrize("svc", sorted(p.parent.name for p in (REPO / "services").glob("*/compose.yml")))
def test_apps_reach_backing_services_through_env(svc):
    """Twelve-factor config: an app's database/cache/queue/storage endpoint
    comes from its .env (DB_HOST, CACHE_HOST, MQ_HOST, S3_ENDPOINT, ...),
    never a container name written into compose, so any tier can move to a
    managed service (or a Kubernetes ConfigMap) without editing compose."""
    if svc in SKIP_SERVICES or svc.startswith("shared-"):
        return
    import yaml
    doc = yaml.safe_load((REPO / "services" / svc / "compose.yml").read_text()) or {}
    names = _backing_names(doc)
    if not names:
        return
    pat = re.compile(r"(?<![\w$.{-])(" + "|".join(map(re.escape, sorted(names, key=len, reverse=True))) + r")(?=[:/;\"'\s]|$)")
    offenders = []
    for name, s in (doc.get("services") or {}).items():
        s = s or {}
        img = str(s.get("image", ""))
        if BACKING_IMAGE.search(img) or SETUP_IMAGES.search(img):
            continue  # the backing service itself, or its own setup job
        env = s.get("environment") or {}
        values = list(env.values()) if isinstance(env, dict) else [e.split("=", 1)[-1] for e in env]
        cmd = s.get("command") or ""
        values += cmd if isinstance(cmd, list) else [cmd]
        for v in values:
            if isinstance(v, str) and pat.search(v):
                offenders.append(f"{name}: {pat.search(v).group(1)} in {v.strip()[:80]!r}")
    assert not offenders, "move these endpoints into .env:\n" + "\n".join(offenders)
