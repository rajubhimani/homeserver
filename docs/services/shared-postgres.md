# Shared Postgres

One Postgres 18 server (`shared-postgres`, `postgres:18.6-alpine`) shared by the services **above CORE** that declare `"shared_db": {"engine": "postgres", ...}` in `services.json`. Each of those apps gets its own database and its own login role, which owns that database and nothing else. CORE and MIN services keep their own `<service>-db` containers; see "Why only above CORE" below.

**Port:** none published (apps reach `shared-postgres:5432` over the `homeserver` network) | **Data:** named volume `shared-postgres_shared-postgres-data` | **Memory:** capped 2G; `shared_buffers=512MB`, `max_connections=300` (compose.yml)

## Setup

```bash
cp services/shared-postgres/.env.example services/shared-postgres/.env
# set POSTGRES_PASSWORD (admin only — never given to any app)
```

Nothing else: you never start it by hand.

## Lifecycle (automatic, reference-counted)

`homeserver.py` manages it; it isn't on any tier (`"tier": "shared"` in `services.json`), so `up all`, `down all`, tier keywords and groups never touch it directly.

- **Start:** any action that can start an app using it (`up`, `update`, `restart`, `restore`, `backup` of a stopped app) first runs `shared_db_ready()`, which starts `shared-postgres` if it isn't running and creates the app's role and database if missing.
- **Stop:** after `down`, `backup` and `restore`, `release_shared_dbs()` checks whether any *running* service still declares this engine. If none does, it stops `shared-postgres` (with the normal volume snapshot of the whole server). So `down daily` keeps it up while an `office` app still uses it, and the last user going down takes it down.
- Counting lives in `main()`, never in `do_up`/`do_down`, because `backup`, `restore` and the proxy swap call `do_down` internally and would otherwise bounce it mid-operation.
- `status` shows it, with the services using it.

## Adding an app to it

1. In `services.json`, add to the app's entry:
   ```json
   "shared_db": {"engine": "postgres", "db": "POSTGRES_DB", "user": "POSTGRES_USER", "password": "POSTGRES_PASSWORD"}
   ```
   Values are **key names in the app's own `.env`**, so no secrets go into `services.json`. Prefix a value with `=` for a literal the app hard-codes (e.g. `"db": "=penpot"`). Add `"extra_dbs": ["name", ...]` for apps that need more than one database (Temporal's `temporal_visibility`).
2. In the app's `compose.yml`: remove its `<service>-db` service, that volume, its `postgres-init/` and every `depends_on: <service>-db`. Point its database host at `shared-postgres`. Compose can't wait on another project's container; `homeserver.py` guarantees the server is healthy before the app starts.
3. Update the app's `docs/services/<app>.md` and `.env.example` in the same pass.

Provisioning (`provision_shared_db`) is idempotent: it creates the role (or resets its password to the `.env` value, so editing `.env` rotates it), creates each database owned by that role, revokes Postgres's default `PUBLIC` `CONNECT`/`TEMP` on it (so no other app's role can even connect to it — verified: `vikunja` → `miniflux` fails with `permission denied for database`), and hands it the `public` schema (Postgres 15+ no longer lets non-owners create objects there), the same thing each per-service `postgres-init/init.sh` used to do.

**App roles aren't superusers.** Under a per-service container the app's `POSTGRES_USER` was that container's superuser; here it only owns its database. Trusted extensions (`pg_trgm`, `pgcrypto`, `uuid-ossp`, `hstore`, `citext`, …) still work, because a database owner can create them. An app that needs an untrusted extension or superuser rights (pgvector, PostGIS, Supabase, Immich) doesn't belong here; keep it on its own container.

## Backups and restore

- An app's snapshot (`down`, `backup`) includes `<app>_shareddb_<db>_<ts>.dump`, a `pg_dump -F c` of just its database(s), next to its volume and `service_data` tarballs.
- `restore <app>` terminates connections, drops the app's database, re-provisions it empty, and runs `pg_restore --no-owner --role <app role>` so every object is owned by the app's role again.
- `dump <app>` writes the same per-database dump to `service_data/db_dump/<app>/`. No roles file, since a `--roles-only` dump of a shared server would carry every app's role and password, and provisioning recreates the app's role from `.env` anyway.
- `migrate` refuses shared-db apps; it only handles a per-service `<service>-db`.
- `reset <app>` (fresh start) snapshots and verifies first, then also drops the app's database(s) and role here, and it starts again with a new empty database. Deleting an app's volumes by hand does **not** remove its database here.
- `shared-postgres` itself gets the usual whole-volume snapshot when it stops, under `service_data/backup/shared-postgres/`.

## Why only above CORE

- CORE holds the always-on, can't-lose data (Vaultwarden, Nextcloud, Immich, Firefly, Forgejo), and Authentik is everyone's login. A shared-server outage must never take those down with it.
- Several CORE databases have hard constraints (Immich's VectorChord image, Plausible's ClickHouse, Authentik's 14–18 range). Separate servers let each upgrade on its own schedule.
- The savings would be small (CORE DBs are already tuned to ~128MB `shared_buffers`), and the per-service backup/restore/migrate tooling already fits them.

Above CORE, apps are opt-in, mostly low-traffic, and nearly all happy on "a current Postgres", which is where one shared server's savings (one set of buffers and background workers instead of ~20) are worth it.

## Users

[wallabag](wallabag.md), [vikunja](vikunja.md), [plane](plane.md), [calcom](calcom.md), [listmonk](listmonk.md), [miniflux](miniflux.md), [airflow](airflow/airflow.md), [dagster](dagster/dagster.md), [temporal](temporal/temporal.md), [n8n](n8n.md), [paperless](paperless.md), [mealie](mealie.md), [nocodb](nocodb.md), [outline](outline.md), [penpot](penpot.md), [documenso](documenso.md), [ghostfolio](ghostfolio.md), [mattermost](mattermost.md), [mail-archiver](mail-archiver.md) (19 services, all above CORE). Special cases:

- **temporal** has two databases (`extra_dbs: ["temporal_visibility"]`).
- **penpot** hard-codes its database and user as `penpot` (`"=penpot"`).
- **dagster** uses `DAGSTER_POSTGRES_*` keys, and its host is in `webserver-daemon/dagster.yaml`, which is baked into the image (rebuild after editing).

Kept on their own database on purpose: appflowy (pgvector, pg16), supabase (custom image and roles), zulip (its own `zulip-postgresql` image), coolify (manages its own DB), plus all of CORE/MIN.

## History

- 2026-10-01: created. Miniflux converted first as the pilot, verified live: auto-start, provisioning (database owned by its role), snapshot dump, backup → delete → restore round trip, and auto-stop when the last user went down.
- 2026-10-01: the remaining 18 above-CORE Postgres apps converted; each brought up and checked healthy on the shared server.
