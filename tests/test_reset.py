"""'reset <service>': snapshot -> verify -> wipe exactly that service -> start
blank. The snapshot must exist and contain everything before anything is
deleted, and 'restore' must be able to undo it."""

from __future__ import annotations

import homeserver as hs
from conftest import shared_db_users

PG = hs.SHARED_DB_SERVICES["postgres"]


def plain_service():
    return next(s for s in hs.SERVICES_DAILY if not hs.shared_db_creds(s))


def seed(fake, svc):
    fake.volumes.add(f"{svc}_data")
    (hs.SERVICE_DATA_ROOT / svc).mkdir(parents=True)
    (hs.SERVICE_DATA_ROOT / svc / "keep.txt").write_text("x")
    fake.running.add(svc)


def test_reset_refuses_without_yes_when_not_interactive(fake, cli):
    svc = plain_service()
    seed(fake, svc)
    fake.events.clear()
    assert cli("prod", "reset", svc) == 1
    assert not fake.events and f"{svc}_data" in fake.volumes, "nothing may happen without confirmation"


def test_reset_snapshots_before_wiping_then_starts_blank(fake, cli):
    svc = plain_service()
    seed(fake, svc)
    fake.events.clear()
    cli("prod", "reset", svc, "-y")
    kinds = [e[0] for e in fake.events]
    assert kinds.index("down") < kinds.index("volume_remove") < len(kinds) - 1 - kinds[::-1].index("up")
    snap = hs.list_snapshots(svc)[-1]
    names = {p.name for p in snap.iterdir()}
    assert f"{svc}_data_{snap.name}.tar.gz" in names and f"service_data_{snap.name}.tar.gz" in names
    assert f"{svc}_data" not in fake.volumes
    assert not (hs.SERVICE_DATA_ROOT / svc).exists()
    assert svc in fake.running, "reset must leave the service running, blank"
    assert not [e for e in fake.events if e[0].startswith("untar")], "start must be fresh, not auto-restored"


def test_reset_deletes_nothing_when_the_snapshot_is_incomplete(fake, cli, monkeypatch):
    svc = plain_service()
    seed(fake, svc)
    monkeypatch.setattr(fake, "tar_volume_to", lambda *a: False)  # volume backup fails
    cli("prod", "reset", svc, "-y")
    assert f"{svc}_data" in fake.volumes
    assert (hs.SERVICE_DATA_ROOT / svc / "keep.txt").exists()
    assert ("volume_remove", f"{svc}_data") not in fake.events


def test_reset_drops_only_this_apps_database_on_the_shared_server(fake, cli, monkeypatch):
    users = shared_db_users("postgres")
    app, other = users[0], users[1]
    cli("prod", "up", app)
    cli("prod", "up", other)
    other_db = hs.shared_db_creds(other)["db"]
    fake.events.clear()
    cli("prod", "reset", app, "-y")
    db = hs.shared_db_creds(app)["db"]
    snap = hs.list_snapshots(app)[-1]
    assert list(snap.glob(f"{app}_shareddb_{db}_*.dump")), "the app's database must be in the snapshot"
    kinds = [(e[0], e[2]) for e in fake.events if e[0] in ("pg_dump", "drop_db", "create_db")]
    assert kinds.index(("pg_dump", db)) < kinds.index(("drop_db", db)) < kinds.index(("create_db", db))
    assert other_db in fake.dbs[PG] and ("drop_db", PG, other_db) not in fake.events
    sql = "\n".join(x["input"] for x in fake.exec_calls)
    assert f'DROP ROLE IF EXISTS "{hs.shared_db_creds(app)["user"]}"' in sql
    assert PG in fake.running and app in fake.running


def test_reset_then_restore_brings_the_database_back(fake, cli):
    app = shared_db_users("postgres")[0]
    db = hs.shared_db_creds(app)["db"]
    cli("prod", "up", app)
    cli("prod", "reset", app, "-y")
    reset_snap = hs.list_snapshots(app)[-1].name
    fake.events.clear()
    cli("prod", "restore", app, "--snapshot", reset_snap)
    assert [e for e in fake.events if e[0] == "pg_restore"], "restore must load the database reset removed"


def test_reset_tier_touches_only_that_tier(fake, cli):
    fake.running |= set(hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY)
    cli("prod", "reset", "daily", "-y")
    reset = {e[1] for e in fake.events if e[0] == "down"} - set(hs.SHARED_DB_SERVICES.values())
    assert reset == set(hs.SERVICES_DAILY)


def test_reset_refuses_a_shared_server(fake, cli):
    fake.running.add(PG)
    assert hs.do_reset(PG, "prod", None) is False
    assert PG in fake.running


def test_reset_removes_root_owned_data_through_the_backend(fake, cli, monkeypatch):
    """Container-created files are root-owned; homeserver.py must never try
    to delete them itself (shutil.rmtree -> PermissionError crashed the first
    real reset run). It goes through BACKEND.remove_dir instead."""
    import shutil
    def denied(*a, **k):
        raise PermissionError("root-owned")
    monkeypatch.setattr(shutil, "rmtree", denied)
    svc = plain_service()
    seed(fake, svc)
    removed = []
    monkeypatch.setattr(fake, "remove_dir", lambda d: removed.append(str(d)) or True)
    cli("prod", "reset", svc, "-y")
    assert str(hs.SERVICE_DATA_ROOT / svc) in removed
    assert svc in fake.running


def test_reset_stops_cleanly_when_the_data_dir_cannot_be_removed(fake, cli, monkeypatch):
    svc = plain_service()
    seed(fake, svc)
    monkeypatch.setattr(fake, "remove_dir", lambda d: False)
    cli("prod", "reset", svc, "-y")
    assert svc not in fake.running, "a partly wiped service must not be started"
    assert hs.list_snapshots(svc), "the pre-wipe snapshot is the way back"
