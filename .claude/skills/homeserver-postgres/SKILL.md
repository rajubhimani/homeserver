---
name: homeserver-postgres
description: Use when adding, tuning, migrating, or debugging a Postgres/MariaDB/RabbitMQ container in this stack — named-volume rules, memory tuning, or a data-directory ownership/corruption error.
---

# Postgres (and MariaDB/RabbitMQ) in this stack

Don't rely on a fixed list of "which services use which DB" here — it goes stale the moment a service is added or changed. Find current state instead:

```bash
# Services with a standalone DB container (postgres/mariadb/rabbitmq image)
grep -l "image:.*\(postgres\|mariadb\|rabbitmq\)" */compose.yml

# Some all-in-one images bundle their DB inside the main container instead of
# a separate `<service>-db` — grep above won't catch these. Look for a named
# volume that isn't an obvious app-data mount instead:
grep -B2 "^volumes:" */compose.yml
```

Then check that service's own `docs/services/<service>.md` — that's where service-specific setup, whether it bundles its own DB internally, custom images, non-default CMDs, and known quirks belong, not here.

Standard setup for a service with its own discrete `<service>-db` container:
- `<service>-db` container using `postgres:18` (or `mariadb`/`rabbitmq` if that's what the app needs — check the app's own docs for which it supports)
- For Postgres: `postgres-init/init.sh` that grants schema ownership — required due to PostgreSQL 15+ default privilege changes
- Healthcheck on the DB so the app container waits until it's ready via `depends_on: condition: service_healthy`

## Named volume, not a bind mount

**DB data always uses a named Docker volume** — declare it in `compose.yml` as e.g. `<service>-postgres:` under `volumes:` and mount it as `<service>-postgres:/var/lib/postgresql` (never `${DATA_ROOT}/postgres:/var/lib/postgresql`). This applies equally to MariaDB (`/var/lib/mysql`) and RabbitMQ (`/var/lib/rabbitmq`).

Why: bind-mounting DB data onto a host filesystem that isn't native Linux ext4 (Windows drvfs, WSL2 9p, macOS osxfs/virtiofs) doesn't give the DB engine reliable POSIX ownership guarantees — causes intermittent `FATAL: data directory has wrong ownership` or worse, silent corruption. Named volumes are daemon-managed and sidestep the host filesystem entirely, so they work identically across Linux/Mac/Windows. Non-DB app data/config/uploads can usually stay on `${DATA_ROOT}` bind mounts — only the DB engine's own data directory needs this.

**Exception — apps that enforce their own ownership checks on non-DB data too** (e.g. Nextcloud's `config.php`/`data/`): `chown` on a Windows Docker Desktop bind mount is unreliable, not structurally broken — treat named volumes as the safer default there too rather than gambling on it. If a service crash-loops or 503s on Windows with permission errors despite the DB being healthy, check whether the *app itself* does its own ownership enforcement — see that service's `docs/services/<service>.md`.

## Migrating existing bind-mounted data into a named volume

```bash
docker run --rm -v <service>_<volname>:/to alpine sh -c "find /to -mindepth 1 -delete"
docker run --rm -v "$(pwd)/service_data/data/<service>/postgres:/from:ro" -v <service>_<volname>:/to alpine sh -c "cp -a /from/. /to/"
docker run --rm -v <service>_<volname>:/to alpine sh -c "chown -R 999:999 /to && chmod 700 /to/*/docker"
```

(999:999 is the `postgres` user in the standard `postgres` images — confirm with `docker run --rm <image> id postgres` first, some custom images differ; a MariaDB image uses a different uid, check the same way.) Verify row counts against the old data before trusting it, then run `uv run homeserver.py <env> backup <service>` to get it into a real tracked snapshot, and only then delete the old bind-mount dir.

**Don't invent ad-hoc `<name>.bak-<timestamp>` folders** next to live data as a manual safety copy — use `backup`/`snapshots` instead (see `homeserver-backups` skill). That ad-hoc pattern predates the snapshot system and just leaves untracked copies nothing prunes or lists.

## Migrating a Postgres container to a different image (e.g. Debian-based to `-alpine`)

**Never just swap the image tag on an existing volume** — Postgres bakes the OS's collation library into the data directory at `initdb` time, and Debian (glibc) vs Alpine (musl) don't agree on collation versions. Reusing the old volume under the new image silently leaves indexes sorted under a stale collation, corrupting sorted/text indexes without an obvious error (see [docker-library/postgres#327](https://github.com/docker-library/postgres/issues/327)). The only safe path is a logical migration: dump the old cluster, `initdb` a genuinely fresh volume under the new image, restore into it, verify, then remove the old volume.

This is built into `homeserver.py` as two commands — use these, don't hand-roll the process:

```bash
uv run homeserver.py dev dump <service>       # pg_dump + pg_dumpall --roles-only -> service_data/db_dump/<service>/<ts>/
uv run homeserver.py dev migrate <service>    # stop, swap image to postgres-alpine + rename volume, fresh DB-only
                                               # start, apply roles, restore, bring the rest back up
uv run homeserver.py dev migrate <service> --image <repo:tag>   # explicit target instead of the -alpine default
```

`migrate` only auto-infers `-alpine` for the plain official `postgres:<tag>` image (no registry/path prefix) — a custom/extended image (e.g. `immich`'s `ghcr.io/immich-app/postgres` with vectorchord/pgvector baked in) requires `--image` explicitly, since there's no way to know whether that specific fork even publishes an alpine (or any other) variant; it refuses to guess. The old volume is never auto-removed — `migrate` prints the exact `docker volume rm` command to run once you've verified (not just "it started" — hit a real API endpoint that reflects actual pre-migration data, a healthy DB-ping isn't enough) it worked.

**Gotchas already handled by `dump`/`migrate`, discovered migrating forgejo/guacamole/nextcloud/jellyfin-pgsql-test — know these exist even though you don't need to work around them by hand:**
- An image whose `docker-entrypoint-initdb.d/` bootstraps its own schema (e.g. guacamole's `01-schema.sql`) collides with the dump trying to recreate the same objects on restore — the restore always runs with `--clean --if-exists`.
- An app authenticating as a DB role other than `POSTGRES_USER` (e.g. Nextcloud's own ad-hoc `oc_admin`, created during its first-run setup and never part of any tracked init script) — a per-database dump never captures roles at all (they're cluster-wide), so `dump` also runs `pg_dumpall --roles-only` and `migrate` applies it before the main restore. See `docs/services/nextcloud.md`'s "Migrated: nextcloud-db..." section for the full incident (Nextcloud crash-looped on `SQLSTATE[08006]: password authentication failed for user "oc_admin"` before this was fixed).

See `docs/services/forgejo.md`'s "Migrated: forgejo-db..." section for the original worked example (before this was built into `homeserver.py`) if you want the full narrative.

## Memory tuning (required on resource-constrained hosts)

Every DB container should get a `command:` override with real tuning parameters, plus a `deploy.resources.limits.memory` cgroup cap as a backstop — not the cap alone. A hard memory cap without tuning the app's own settings just means the DB tries to use more than the cap and gets OOM-killed under load; tuning the engine's own settings down means it rarely approaches the cap at all.

General principle, not a fixed per-service table:
- **Single-consumer DB** (only one app connects to it): lower `max_connections`/`shared_buffers`/`effective_cache_size`, smaller memory cap (roughly 128MB shared_buffers / 20 connections / 384M cap as a starting point).
- **Multi-consumer or high-throughput DB** (several concurrent workers, or a large sync-heavy app): higher `max_connections`/`effective_cache_size`, larger cap (roughly 50 connections / 512M cap as a starting point).
- Check a few existing `<service>/compose.yml` files' `command:` overrides for concrete, currently-applied values to copy from and adjust — treat those as worked examples, not this skill, as the source of truth (they can drift from any numbers written here).
- **Before assuming a new DB container needs no tuning**, check whether it already has one — `grep -l "command:.*shared_buffers\|command:.*max_connections" */compose.yml` shows which ones do. A DB container with neither a `command:` override nor a `deploy.resources.limits.memory` cap is a gap worth fixing, not a sign it doesn't need one — this includes all-in-one images that bundle their own DB just as much as a discrete `<service>-db` container (check that service's own `docs/services/<service>.md` for whether it does).
- Some official images override the default `CMD` for their own reasons (e.g. to point at a non-default config file enabling extensions/preload libraries) — if you replace `command:` on such an image without preserving its original first flag, the app can silently fall back to defaults and break in ways that look unrelated (e.g. a vector-search extension disappearing). Check the image's own docs/Dockerfile for its default `CMD` before overriding it — see that service's own `docs/services/<service>.md` for a worked example if one's already documented there.
- After changing a `command:`/`deploy:` block, only the DB container needs recreating — much faster than a full service restart:
  ```bash
  cd <service>/
  docker compose -f compose.yml -f compose.prod.yml up -d --no-deps <service>-db
  ```
- Verify tuning actually applied: `docker exec <service>-db psql -U <postgres-user> -c "SHOW max_connections; SHOW shared_buffers;"` (or the MariaDB/RabbitMQ equivalent — `SHOW VARIABLES LIKE '...'` / `rabbitmq-diagnostics`).
