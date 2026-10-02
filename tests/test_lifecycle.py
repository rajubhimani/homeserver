"""Tier cascades, down semantics, bundles/requires, snapshots and auto-restore —
the CLI behaviour documented in CLAUDE.md, run through the real main()."""

from __future__ import annotations

import homeserver as hs

ALL_TIERS = (
    hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER
    + hs.SERVICES_OFFICE + hs.SERVICES_AUTOMATION_AI + hs.SERVICES_EXTRA
)


def ups(fake):
    return [e[1] for e in fake.events if e[0] == "up"]


def downs(fake):
    return [e[1] for e in fake.events if e[0] == "down"]


def test_tier_lists_are_disjoint_and_cover_every_managed_service():
    lists = [hs.SERVICES_MIN, hs.SERVICES_CORE, hs.SERVICES_DAILY, hs.SERVICES_BROWSER,
             hs.SERVICES_OFFICE, hs.SERVICES_AUTOMATION_AI, hs.SERVICES_EXTRA, hs.SERVICES_MANUAL]
    flat = [s for lst in lists for s in lst]
    assert len(flat) == len(set(flat)), "a service is in two tiers"
    managed = {s["slug"] for s in hs._SERVICES_DATA["services"]
               if hs.is_managed_service(s) and s["tier"] != "shared"}
    assert set(flat) == managed


def test_up_core_bootstraps_min_first_when_nothing_runs(fake, cli):
    cli("prod", "up", "core")
    started = ups(fake)
    assert set(hs.SERVICES_MIN + hs.SERVICES_CORE) <= set(started)
    last_min = max(started.index(s) for s in hs.SERVICES_MIN)
    first_core = min(started.index(s) for s in hs.SERVICES_CORE)
    assert last_min < first_core, "MIN must be up before CORE starts"


def test_up_core_leaves_running_min_untouched(fake, cli):
    fake.running |= set(hs.SERVICES_MIN)
    cli("prod", "up", "core")
    assert not set(ups(fake)) & set(hs.SERVICES_MIN)


def test_up_core_never_implies_higher_tiers(fake, cli):
    cli("prod", "up", "core")
    higher = hs.SERVICES_DAILY + hs.SERVICES_BROWSER + hs.SERVICES_OFFICE + hs.SERVICES_AUTOMATION_AI + hs.SERVICES_EXTRA
    assert not set(ups(fake)) & set(higher)


def test_up_office_bootstraps_only_missing_lower_tiers(fake, cli):
    fake.running |= set(hs.SERVICES_MIN + hs.SERVICES_CORE)
    cli("prod", "up", "office")
    started = set(ups(fake))
    assert set(hs.SERVICES_DAILY + hs.SERVICES_BROWSER + hs.SERVICES_OFFICE) <= started
    assert not started & set(hs.SERVICES_MIN + hs.SERVICES_CORE)


def test_up_all_never_starts_manual_services(fake, cli):
    cli("prod", "up", "all")
    assert set(ALL_TIERS) <= set(ups(fake))
    assert not set(ups(fake)) & set(hs.SERVICES_MANUAL)


def test_down_tier_stops_only_that_tier_in_reverse_order(fake, cli):
    fake.running |= set(ALL_TIERS)
    cli("prod", "down", "daily")
    stopped = [s for s in downs(fake) if s not in hs.SHARED_DB_SERVICES.values()]
    assert stopped == list(reversed(hs.SERVICES_DAILY))


def test_down_core_leaves_min_running(fake, cli):
    fake.running |= set(hs.SERVICES_MIN + hs.SERVICES_CORE)
    cli("prod", "down", "core")
    assert set(hs.SERVICES_MIN) <= fake.running


def test_down_all_stops_everything_including_running_manual(fake, cli):
    """CLAUDE.md: 'down all — the one command that stops everything'."""
    fake.running |= set(ALL_TIERS + hs.SERVICES_MANUAL)
    cli("prod", "down", "all")
    service_names = set(ALL_TIERS + hs.SERVICES_MANUAL)
    assert not fake.running & service_names
    order = [s for s in downs(fake) if s in ALL_TIERS]
    assert order == list(reversed(ALL_TIERS)), "down all must stop tiers in reverse startup order"


def test_bundle_requires_apply_to_up_but_never_to_down(fake, cli):
    """services.json 'requires' (Browser Hub needs nginx-plain) is spliced
    into up-family actions only; 'down' must never stop shared infra."""
    bundle, required = next((b, r) for b, r in hs.BUNDLE_REQUIRES.items() if r)
    cli("prod", "up", f"group:{bundle}")
    assert set(required) <= set(ups(fake))

    fake.events.clear()
    fake.running |= set(hs.BUNDLE_MEMBERS[bundle]) | set(required)
    cli("prod", "down", f"group:{bundle}")
    assert not set(required) & set(downs(fake))
    assert set(required) <= fake.running


def test_group_targets_cover_category_members(fake, cli):
    group, members = next((g, m) for g, m in hs.SERVICE_GROUPS.items() if len(m) > 1 and g not in hs.BUNDLE_MEMBERS)
    cli("prod", "up", f"group:{group}")
    assert set(members) <= set(ups(fake))


def test_down_snapshots_volumes_and_data_and_prunes(fake, cli, monkeypatch):
    svc = hs.SERVICES_DAILY[0]
    fake.volumes.add(f"{svc}_data")
    (hs.SERVICE_DATA_ROOT / svc).mkdir(parents=True)
    monkeypatch.setattr(hs, "BACKUP_RETENTION", 2)
    stamps = iter(f"20260101-00000{i}" for i in range(5))
    monkeypatch.setattr(hs.time, "strftime", lambda fmt: next(stamps))
    for _ in range(3):
        fake.running.add(svc)
        cli("prod", "down", svc)
    snaps = hs.list_snapshots(svc)
    assert [p.name for p in snaps] == ["20260101-000001", "20260101-000002"], "retention must keep the newest N"
    names = {p.name for p in snaps[-1].iterdir()}
    assert names == {f"service_data_{snaps[-1].name}.tar.gz", f"{svc}_data_{snaps[-1].name}.tar.gz"}


def test_down_no_backup_skips_snapshot(fake, cli):
    svc = hs.SERVICES_DAILY[0]
    fake.volumes.add(f"{svc}_data")
    fake.running.add(svc)
    cli("prod", "down", svc, "--no-backup")
    assert not hs.list_snapshots(svc)


def test_up_auto_restores_when_volumes_and_data_are_missing(fake, cli):
    svc = hs.SERVICES_DAILY[0]
    snap = hs.BACKUP_ROOT / svc / "20260101-000000"
    snap.mkdir(parents=True)
    (snap / f"{svc}_data_20260101-000000.tar.gz").write_bytes(b"tar")
    cli("prod", "up", svc)
    assert ("untar_volume", f"{svc}_data") in fake.events


def test_up_fresh_skips_auto_restore(fake, cli):
    svc = hs.SERVICES_DAILY[0]
    snap = hs.BACKUP_ROOT / svc / "20260101-000000"
    snap.mkdir(parents=True)
    (snap / f"{svc}_data_20260101-000000.tar.gz").write_bytes(b"tar")
    cli("prod", "up", svc, "--fresh")
    assert not [e for e in fake.events if e[0].startswith("untar")]


def test_up_with_existing_volume_does_not_restore(fake, cli):
    svc = hs.SERVICES_DAILY[0]
    fake.volumes.add(f"{svc}_data")
    snap = hs.BACKUP_ROOT / svc / "20260101-000000"
    snap.mkdir(parents=True)
    (snap / f"{svc}_data_20260101-000000.tar.gz").write_bytes(b"tar")
    cli("prod", "up", svc)
    assert not [e for e in fake.events if e[0].startswith("untar")]


def test_backup_of_running_service_restarts_it(fake, cli):
    svc = hs.SERVICES_DAILY[0]
    fake.volumes.add(f"{svc}_data")
    fake.running.add(svc)
    cli("prod", "backup", svc)
    assert svc in fake.running
    assert hs.list_snapshots(svc)


def test_backup_of_stopped_service_leaves_it_stopped(fake, cli):
    svc = hs.SERVICES_DAILY[0]
    fake.volumes.add(f"{svc}_data")
    cli("prod", "backup", svc)
    assert svc not in fake.running


def test_unknown_env_is_rejected(fake, cli):
    assert cli("staging", "up", "core") == 1
    assert not fake.events


def test_hand_made_backup_folders_are_never_the_latest_snapshot(fake, cli, monkeypatch):
    """A manual folder like 'pre-upgrade-fix-20260817-232941' sorts after every
    timestamp; it must never be restored as 'latest' or pruned (2026-10-02)."""
    svc = hs.SERVICES_DAILY[0]
    root = hs.BACKUP_ROOT / svc
    for name in ("20260101-000000", "20260102-000000", "pre-upgrade-fix-20250817-232941"):
        (root / name).mkdir(parents=True)
        (root / name / f"{svc}_data_{name}.tar.gz").write_bytes(b"tar")
    assert [p.name for p in hs.list_snapshots(svc)] == ["20260101-000000", "20260102-000000"]
    monkeypatch.setattr(hs, "BACKUP_RETENTION", 1)
    hs.prune_snapshots(svc)
    assert (root / "pre-upgrade-fix-20250817-232941").is_dir(), "manual folders are never pruned"
    assert [p.name for p in hs.list_snapshots(svc)] == ["20260102-000000"]


def test_down_of_an_already_stopped_service_takes_no_snapshot(fake, cli):
    """Its last snapshot is still current; another one would only churn
    retention (and, for a shared-db app, be incomplete)."""
    svc = hs.SERVICES_DAILY[0]
    fake.volumes.add(f"{svc}_data")
    cli("prod", "down", svc)
    assert not hs.list_snapshots(svc)


def test_down_all_snapshots_only_what_was_running(fake, cli):
    running_svc, stopped_svc = hs.SERVICES_DAILY[0], hs.SERVICES_DAILY[1]
    for s in (running_svc, stopped_svc):
        fake.volumes.add(f"{s}_data")
    fake.running.add(running_svc)
    cli("prod", "down", "all")
    assert hs.list_snapshots(running_svc)
    assert not hs.list_snapshots(stopped_svc)


def test_explicit_backup_of_a_stopped_service_still_snapshots(fake, cli):
    svc = hs.SERVICES_DAILY[0]
    fake.volumes.add(f"{svc}_data")
    cli("prod", "backup", svc)
    assert hs.list_snapshots(svc), "backup was asked for explicitly"


def test_reset_of_a_stopped_service_still_snapshots_before_wiping(fake, cli):
    svc = hs.SERVICES_DAILY[0]
    fake.volumes.add(f"{svc}_data")
    cli("prod", "reset", svc, "-y")
    snap = hs.list_reset_backups(svc)[0]
    assert any(p.name.startswith(f"{svc}_data_") for p in snap.iterdir())


def test_restore_from_a_renamed_snapshot_folder_uses_the_real_volume_names(fake, cli):
    """A snapshot kept out of pruning under a descriptive name must restore
    into the original volumes, not '<vol>_<timestamp>'."""
    svc = hs.SERVICES_DAILY[0]
    kept = hs.BACKUP_ROOT / svc / "pre-fresh-install-20261002-112217"
    kept.mkdir(parents=True)
    (kept / f"{svc}_data_20261002-112217.tar.gz").write_bytes(b"tar")
    cli("prod", "restore", svc, "--snapshot", kept.name)
    assert ("untar_volume", f"{svc}_data") in fake.events
