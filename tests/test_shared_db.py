"""Shared Postgres/MariaDB for services above CORE: reference-counted start/
stop, provisioning, per-app snapshot dumps and restore. See
docs/services/shared-postgres.md for the requirements these encode."""

from __future__ import annotations

import pytest

import homeserver as hs
from conftest import shared_db_users

PG = hs.SHARED_DB_SERVICES["postgres"]
MY = hs.SHARED_DB_SERVICES["mariadb"]


@pytest.fixture
def pg_users(monkeypatch):
    """Two Postgres users of the shared server. Uses real services.json
    entries; if fewer than two are converted yet, borrows a Postgres app
    from above CORE so the multi-user rules are still exercised."""
    users = shared_db_users("postgres")
    if len(users) < 2:
        spare = next(s for s in ["listmonk", "n8n", "outline"] if s not in users)
        entry = dict(hs._SERVICES_BY_SLUG[spare])
        entry["shared_db"] = {"engine": "postgres", "db": "POSTGRES_DB", "user": "POSTGRES_USER", "password": "POSTGRES_PASSWORD"}
        monkeypatch.setitem(hs._SERVICES_BY_SLUG, spare, entry)
        users = users + [spare]
    return users[:2]


def ups(fake):
    return [e[1] for e in fake.events if e[0] == "up"]


# ── registration ──────────────────────────────────────────────────

def test_shared_servers_are_in_no_tier_list():
    every_tier = (hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER
                  + hs.SERVICES_OFFICE + hs.SERVICES_AUTOMATION_AI + hs.SERVICES_EXTRA + hs.SERVICES_MANUAL)
    for server in hs.SHARED_DB_SERVICES.values():
        assert server not in every_tier
        assert hs._SERVICES_BY_SLUG[server]["tier"] == "shared"
        assert hs.is_valid_service(server), "shared servers must stay addressable for logs/snapshots"


def test_core_and_min_never_use_a_shared_database():
    for svc in hs.SERVICES_MIN + hs.SERVICES_CORE:
        assert not hs.shared_db_creds(svc), f"{svc} is CORE/MIN and must keep its own database"


def test_creds_resolve_env_keys_literals_and_extra_dbs(fake, monkeypatch):
    svc = shared_db_users("postgres")[0]
    entry = dict(hs._SERVICES_BY_SLUG[svc])
    entry["shared_db"] = {"engine": "postgres", "db": "=litdb", "user": "POSTGRES_USER",
                          "password": "POSTGRES_PASSWORD", "extra_dbs": ["second"]}
    monkeypatch.setitem(hs._SERVICES_BY_SLUG, svc, entry)
    c = hs.shared_db_creds(svc)
    assert c["db"] == "litdb"
    assert c["user"] and c["password"], "keys must resolve from the service's .env(.example)"
    assert c["extra_dbs"] == ["second"]
    assert c["container"] == PG


# ── reference-counted lifecycle ───────────────────────────────────

def test_up_starts_shared_server_before_the_app(fake, cli, pg_users):
    app = pg_users[0]
    cli("prod", "up", app)
    order = ups(fake)
    assert order.index(PG) < order.index(app)
    assert {PG, app} <= fake.running


def test_down_of_last_user_stops_shared_server(fake, cli, pg_users):
    app = pg_users[0]
    cli("prod", "up", app)
    cli("prod", "down", app)
    assert PG not in fake.running


def test_shared_server_stays_up_while_another_user_runs(fake, cli, pg_users):
    a, b = pg_users
    cli("prod", "up", a)
    cli("prod", "up", b)
    cli("prod", "down", a)
    assert PG in fake.running
    cli("prod", "down", b)
    assert PG not in fake.running


def test_down_of_unrelated_service_keeps_shared_server(fake, cli, pg_users):
    cli("prod", "up", pg_users[0])
    other = next(s for s in hs.SERVICES_DAILY if not hs.shared_db_creds(s))
    fake.running.add(other)
    cli("prod", "down", other)
    assert PG in fake.running


def test_down_core_never_touches_shared_server(fake, cli, pg_users):
    cli("prod", "up", pg_users[0])
    fake.running |= set(hs.SERVICES_CORE)
    cli("prod", "down", "core")
    assert PG in fake.running


def test_down_all_stops_shared_servers_last(fake, cli, pg_users):
    cli("prod", "up", pg_users[0])
    cli("prod", "down", "all")
    downs = [e[1] for e in fake.events if e[0] == "down"]
    assert downs[-1] == PG
    assert PG not in fake.running


def test_backup_of_running_app_never_bounces_shared_server(fake, cli, pg_users):
    app = pg_users[0]
    cli("prod", "up", app)
    fake.events.clear()
    cli("prod", "backup", app)
    assert ("down", PG) not in fake.events
    assert {PG, app} <= fake.running


def test_backup_of_stopped_app_dumps_db_then_releases_server(fake, cli, pg_users):
    app = pg_users[0]
    cli("prod", "up", app)
    cli("prod", "down", app)
    cli("prod", "backup", app)
    snap = hs.list_snapshots(app)[-1]
    assert list(snap.glob(f"{app}_shareddb_*.dump")), "a stopped app's backup must still include its database"
    assert PG not in fake.running


def test_restore_releases_server_when_app_stays_stopped(fake, cli, pg_users):
    app = pg_users[0]
    cli("prod", "up", app)
    cli("prod", "down", app)
    cli("prod", "restore", app)
    assert app not in fake.running
    assert PG not in fake.running


# ── provisioning ──────────────────────────────────────────────────

def test_provisioning_creates_db_owned_by_app_role_once(fake, cli, pg_users):
    app = pg_users[0]
    c = hs.shared_db_creds(app)
    cli("prod", "up", app)
    assert c["db"] in fake.dbs[PG]
    creates = [e for e in fake.events if e[0] == "create_db" and e[2] == c["db"]]
    sql = "\n".join(x["input"] for x in fake.exec_calls)
    assert f'OWNER "{c["user"]}"' in sql
    assert f'ALTER SCHEMA public OWNER TO "{c["user"]}"' in sql
    assert f'REVOKE ALL ON DATABASE "{c["db"]}" FROM PUBLIC' in sql, "other apps' roles must not be able to connect"
    cli("prod", "down", app)
    cli("prod", "up", app)
    assert [e for e in fake.events if e[0] == "create_db" and e[2] == c["db"]] == creates, "provisioning must be idempotent"


def test_passwords_never_appear_in_exec_argv(fake, cli, pg_users):
    for engine in ("postgres", "mariadb"):
        users = pg_users if engine == "postgres" else shared_db_users("mariadb")
        for app in users[:1]:
            cli("prod", "up", app)
    secrets = {hs.shared_admin(e)[1] for e in hs.SHARED_DB_SERVICES}
    secrets |= {hs.shared_db_creds(a)["password"] for a in pg_users + shared_db_users("mariadb")}
    for call in fake.exec_calls:
        for secret in filter(None, secrets):
            assert not any(secret in arg for arg in call["cmd"]), f"password leaked into argv: {call['cmd']}"


@pytest.mark.skipif(not shared_db_users("mariadb"), reason="no service uses shared-mariadb yet")
def test_mariadb_provisioning_grants_only_the_apps_database(fake, cli):
    app = shared_db_users("mariadb")[0]
    c = hs.shared_db_creds(app)
    cli("prod", "up", app)
    sql = "\n".join(x["input"] for x in fake.exec_calls if x["container"] == MY)
    assert f"GRANT ALL PRIVILEGES ON `{c['db']}`.*" in sql
    assert "ON *.*" not in sql
    assert all("MYSQL_PWD" in x["env"] for x in fake.exec_calls if x["container"] == MY)


def test_identifier_and_literal_escaping():
    assert hs._pg_ident('a"b') == '"a""b"'
    assert hs._sql_literal("it's") == "'it''s'"
    assert hs._my_ident("a`b") == "`a``b`"


# ── snapshots, restore, dump, migrate ─────────────────────────────

def test_down_snapshot_contains_the_apps_database_dump(fake, cli, pg_users):
    app = pg_users[0]
    cli("prod", "up", app)
    cli("prod", "down", app)
    snap = hs.list_snapshots(app)[-1]
    db = hs.shared_db_creds(app)["db"]
    assert [p.name for p in snap.glob("*_shareddb_*")] == [f"{app}_shareddb_{db}_{snap.name}.dump"]


def test_restore_drops_reprovisions_and_loads_as_app_role(fake, cli, pg_users):
    app = pg_users[0]
    c = hs.shared_db_creds(app)
    cli("prod", "up", app)
    cli("prod", "backup", app)
    fake.events.clear()
    cli("prod", "restore", app)
    kinds = [e[0] for e in fake.events]
    assert kinds.index("drop_db") < kinds.index("create_db") < kinds.index("pg_restore")
    restore_cmd = next(e[2] for e in fake.events if e[0] == "pg_restore")
    assert restore_cmd[restore_cmd.index("--role") + 1] == c["user"]
    assert app in fake.running, "restore must leave a running app running"


def test_up_auto_restores_shared_db_only_when_it_is_missing(fake, cli, pg_users):
    app = pg_users[0]
    db = hs.shared_db_creds(app)["db"]
    snap = hs.BACKUP_ROOT / app / "20260101-000000"
    snap.mkdir(parents=True)
    (snap / f"{app}_shareddb_{db}_20260101-000000.dump").write_bytes(b"PGDUMP")
    cli("prod", "up", app)
    assert [e for e in fake.events if e[0] == "pg_restore"], "missing db + snapshot must auto-restore"
    fake.events.clear()
    cli("prod", "down", app, "--no-backup")
    cli("prod", "up", app)
    assert not [e for e in fake.events if e[0] == "pg_restore"], "existing db must not be overwritten"


def test_dump_targets_shared_server_without_roles_file(fake, cli, pg_users):
    app = pg_users[0]
    cli("prod", "up", app)
    cli("prod", "dump", app)
    dump_dir = hs.list_dumps(app)[-1]
    names = [p.name for p in dump_dir.iterdir()]
    assert any("_shareddb_" in n for n in names)
    assert not any("_roles_" in n for n in names), "a shared server's roles dump would leak every app's password"


def test_migrate_refuses_shared_db_apps(fake, cli, pg_users):
    assert hs.do_migrate(pg_users[0], "prod", None) is False
