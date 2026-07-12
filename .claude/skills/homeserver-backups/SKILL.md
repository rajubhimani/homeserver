---
name: homeserver-backups
description: Use when backing up, restoring, listing snapshots, or migrating this homeserver stack to a different machine.
---

# Backups, snapshots, and machine migration

Unlike a traditional "remember to back up" workflow, **`down` automatically snapshots a service every time it stops** — its named volumes and `service_data/data/<service>/` tree get tarred into a new timestamped folder under `service_data/backup/<service>/<YYYYMMDD-HHMMSS>/`. This is the default so that day-to-day use (stopping a service to change config, restarting after an update, etc.) can never accidentally skip a safety copy.

```bash
# down always snapshots first (default) — add --no-backup to skip when you
# genuinely don't want the snapshot churn (e.g. a trivial config-reload restart)
uv run homeserver.py dev down <service>
uv run homeserver.py dev down <service> --no-backup

# Explicit backup without mentally modeling stop-then-restart — same effect
# as down (snapshots), but restarts the service afterward if it was running
uv run homeserver.py dev backup all
uv run homeserver.py dev backup <service>

# List available snapshots for a service
uv run homeserver.py dev snapshots <service>

# Restore the latest snapshot (also auto-snapshots current state first, via
# the same auto-backup-on-down behavior, so restoring is itself non-destructive)
uv run homeserver.py dev restore all
uv run homeserver.py dev restore <service>

# Restore a specific snapshot instead of the latest
uv run homeserver.py dev restore <service> --snapshot 20260710-160628
```

Snapshots beyond `BACKUP_RETENTION` (root `.env`, default 5) are auto-pruned oldest-first after each backup; set `BACKUP_RETENTION=-1` for unlimited history (manual cleanup only).

## Migrating to a different machine

`backup all`, copy the whole `service_data/backup/` folder to the new machine (plain `.tar.gz` files — pendrive-safe, ownership preserved as tar metadata not filesystem metadata), clone this repo, `restore all`.

**Never copy `service_data/data/` directly between machines with different OSes/filesystems** — see the `homeserver-postgres` skill's named-volume section for why (DB data isn't even under `service_data/data/` for that reason; it's a named volume, correctly captured by `backup`/`restore` via `docker volume` tar/untar instead).

## Layout

```text
service_data/               ← gitignored entirely
  data/                     ← live data, bind-mounted into running containers (app data only —
                               DB data is a named volume, not here — see homeserver-postgres skill)
  backup/                   ← timestamped snapshots
    <service>/
      <timestamp>/
        <service>_<volume-name>.tar.gz   ← one per named volume
        service_data.tar.gz              ← the data/<service>/ tree
```

**A folder under `service_data/data/` is safe to delete only if it doesn't exist there in the first place** — never delete anything under `data/`, that's always live. Folders under `service_data/backup/<service>/<timestamp>/` are point-in-time snapshots, safe to delete individually once you don't need that point in time (auto-pruning already does this beyond `BACKUP_RETENTION`).
