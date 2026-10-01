# 15 — Starting & Stopping Services

Every lifecycle command goes through `homeserver.py`:

```bash
uv run homeserver.py <dev|prod> <action> <target> [flags]
```

- **`dev`** publishes ports on all interfaces.
- **`prod`** binds them to `127.0.0.1` and wg-easy's tunnel address `10.8.0.1` only (see [09 — Firewall](09-firewall.md)).
- **Targets** can be one or more service names, a tier keyword (`min`, `core`, `daily`, `browser`, `office`, `automation-ai`, `all`), `group:<category-or-subcategory>`, or a bundle name such as `browser`.

## Commands that start services

| Command | What it does |
|---|---|
| `up <service> [<service>...]` | Starts the named services. Already-running ones are left alone (plain `compose up -d`, no recreate). Waits until each is healthy. |
| `up <tier>` (`core`, `daily`, `browser`, `office`, `automation-ai`) | Starts that tier, first starting any **lower** tiers that aren't running. It never pulls in **higher** tiers: `up core` never starts `daily`. |
| `up min` / `up all` | Starts the full list every time. `all` covers MIN through EXTRA, never MANUAL (GitLab). |
| `up group:<name>` | Starts every service sharing that category or subcategory, e.g. `group:notes`. Bundle groups also start what they `requires` (Browser Hub starts `nginx-plain`). |
| `up <bundle>` (e.g. `browser`) | The bundle's members plus whatever they `requires`. |
| `restart <target>` | Recreates the containers (`--force-recreate`) to pick up `.env`/compose changes, then waits until healthy. Starts the service if it was stopped. |
| `update <target>` / `update running` | Pulls newer images, recreates and waits until healthy. `running` = only what's up now. |
| `precreate <target> [--update]` | Creates containers **without starting them**, so they appear in Portainer. `--update` rebuilds stopped ones after config changes and never touches running ones. |
| `restore <service> [--snapshot <ts>]` | Snapshots the current state first, loads the snapshot (latest by default), and starts the service again if it was running. |
| `reset <service\|tier>` | Takes a verified snapshot, wipes that service only, and starts it empty. You must type `reset`, or pass `-y`. Undo with `restore`. See [08 — Maintenance](08-maintenance.md#fresh-start-of-a-service-reset). |

## Flags

| Flag | Effect |
|---|---|
| `--fresh` (`up` only) | Skips the auto-restore described below. It deletes nothing; use `reset` for a real fresh start. |
| `--profile <name>` | Also starts that Compose profile's containers, e.g. GitLab's CI runner. |
| `--no-ml` (`up immich` only) | Starts Immich without its machine-learning container. |
| `--no-backup` (`down`) | Stops without taking a snapshot. |
| `--snapshot <ts>` (`restore`) | Restores a specific snapshot instead of the latest (`snapshots <service>` lists them). |
| `--image <repo:tag>` (`migrate`) | The Postgres image to migrate a per-service `<service>-db` to. |
| `-y` / `--yes` | Skips the confirmation that tier, group and bundle commands show, and is required for a non-interactive `reset`. |

## What happens automatically during any start

1. **Shared database:** if the service uses one (`"shared_db"` in `services.json`), [shared-postgres](services/shared-postgres.md) or [shared-mariadb](services/shared-mariadb.md) starts first if it isn't already running, and the service's own database and login are created if missing. An existing database is never wiped.
2. **Auto-restore:** if the service has **no** volumes, **no** `service_data/data/<service>/` folder and **no** database on its shared server, but a snapshot exists, `up` restores the snapshot before starting. `--fresh` skips this.
3. **WireGuard:** in `prod`, `wg-easy` starts first if its tunnel address isn't up yet, because every service binds a port to `10.8.0.1`.
4. **Proxy swap:** starting `nginx-plain` stops `nginx` (Nginx Proxy Manager), and vice versa. Only one proxy can hold ports 80/443.
5. **Forced reload:** `landing` and `nginx-plain` are always restarted on `up` so their templates pick up config changes.
6. **Data-drive check:** a service refuses to start if its data sits on a drive from `/etc/fstab` that isn't mounted, or is mounted read-only.

## Stopping

- **`down <target>`:** stops the service and takes a snapshot (`--no-backup` skips the snapshot). A tier keyword stops **only** that tier, in reverse order, never the lower ones. `down all` stops everything in reverse order, including running MANUAL services.
- **`down group:<bundle>`:** never stops the bundle's `requires` infrastructure (e.g. `nginx-plain` keeps running after `down group:browser`).
- **Shared database servers:** they stop automatically when the last service using them goes down. They're also kept up through `backup`/`restore` of a running app.

## Other actions

| Command | What it does |
|---|---|
| `backup <target>` | Takes a snapshot (stops and restarts a running service around it). |
| `snapshots <service>` | Lists a service's snapshots. |
| `dump <service>` | Logical database dump to `service_data/db_dump/<service>/`, for a per-service `<service>-db` or the app's own database on a shared server. |
| `migrate <service> [--image <repo:tag>]` | Moves a per-service `<service>-db` to a different Postgres image via dump and restore (refuses shared-database apps). |
| `logs <service>` | Follows the service's logs. |
| `status` / `ps` | What's running, by tier and group, plus the shared database servers and who uses them. |

## Tests

Every behaviour on this page is covered by `uv run pytest` (`tests/test_lifecycle.py`, `tests/test_shared_db.py`, `tests/test_reset.py`). `tests/test_repo_invariants.py` also fails if `homeserver.py` gains an action or flag this page doesn't mention.
