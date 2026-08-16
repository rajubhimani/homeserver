# AppFlowy

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Open-source Notion alternative — docs, databases, kanban, and AI writing tools.
**Port:** `8103` (host) → `80` (container, `appflowy-nginx`) | **Data:** `service_data/data/appflowy/` | **Requires:** Postgres (pgvector) + Redis + MinIO | **Memory:** no hard limit set in compose.yml; measured idle ~382MB across all 8 containers (appflowy-cloud is the largest single piece at ~121MB). No official RAM figure exists upstream — AppFlowy's own `docker-compose.yml` uses unpinned `latest` tags with no published resource spec, so treat any number here (including this one) as observed, not guaranteed

## Setup

```bash
cp services/appflowy/.env.example services/appflowy/.env
# generate: openssl rand -hex 32 → GOTRUE_JWT_SECRET
# set POSTGRES_PASSWORD and MINIO_ROOT_PASSWORD
mkdir -p service_data/data/appflowy/minio
uv run homeserver.py dev up appflowy
```

## First login

- Browse to `http://<ip>:8103` — create account and workspace
- Admin UI: `http://<ip>:8103/web/` — manage users and workspaces
- GoTrue auth: `https://appflowy.yourdomain.com/gotrue/`
- Desktop/mobile clients connect directly to `https://appflowy.yourdomain.com`

> The `appflowy-minio-setup` container runs once to create the `appflowy` S3 bucket, then exits — this is normal, not a crash.

## Architecture

Multi-container: postgres (pgvector), redis, minio, gotrue, appflowy-cloud, appflowy-web, admin-frontend, nginx. `GOTRUE_JWT_SECRET` must be at least 32 chars and **identical** across gotrue and appflowy-cloud (`openssl rand -hex 32`).

### Compatible image versions

All services below must stay in sync. `appflowy_web` uses its own versioning scheme — `0.15.5` is the current latest for the web frontend regardless of cloud version.

| Service | Image | Version | Notes |
| --- | --- | --- | --- |
| Cloud backend | `appflowyinc/appflowy_cloud` | `0.16.5` | Pinned independently — not currently in lockstep with gotrue/admin |
| Auth service | `appflowyinc/gotrue` | `0.17.1` | Must match admin |
| Admin UI | `appflowyinc/admin_frontend` | `0.17.1` | Must match gotrue |
| Web frontend | `appflowyinc/appflowy_web` | `0.16.2` | Own versioning scheme — nginx rewrite handles path differences |
| Database | `pgvector/pgvector` | `pg16` | — |
| Cache | `redis` | `8.10-alpine` | — |

> **WebSocket path difference:** `appflowy_web:0.15.5` sends WebSocket requests to `/ws/{workspace_id}/` but `appflowy_cloud:0.16.x` changed to `/ws/v2/{workspace_id}`. The internal nginx (`appflowy/nginx.conf`) rewrites the path automatically.

## Known issues and fixes

### "Database error finding user" on signup

GoTrue's own migrations always fully-qualify their schema (`{{Namespace}}.users`, baked into the Go template, default namespace `auth`), so they're unaffected by `search_path`. But GoTrue's everyday runtime queries (login, etc.) and its own internal migration-tracking table lookup are unqualified and depend on the DB connection's `search_path` resolving to `auth` — without it you get `relation "users" does not exist` on login even though the tables clearly exist.

AppFlowy Cloud (the Rust service)'s sqlx migrations, on the other hand, assume unqualified names resolve to `public` — a later migration hardcodes `public.af_user`. Since both services share the same DB role, a role-wide `ALTER ROLE ... SET search_path` (an earlier version of this setup) forces one choice for both and breaks the other.

**Fix:** scope `search_path=auth,public` to **only** GoTrue's own connection string via the Postgres URI's `options` param (`?options=-c%20search_path%3Dauth%2Cpublic` on `GOTRUE_DB_DATABASE_URL`), leaving `APPFLOWY_DATABASE_URL` (and the role default) at plain `public`. This is baked directly into `GOTRUE_DB_DATABASE_URL` in `compose.yml`, so it applies automatically on every start — no init script involved.

### Migration tracking split — applies when upgrading or after container recreation on an existing DB

AppFlowy uses two migration trackers:

| Service | Tracking table | Schema |
| --- | --- | --- |
| GoTrue | `schema_migrations` | `auth` (pre-seeded 55 rows) and `public` (full 70 rows) |
| AppFlowy Cloud | `_sqlx_migrations` | `auth` (pre-seeded 8 rows) and `public` (full 144 rows) |

After setting `search_path=auth,public` on an existing DB, both services find the incomplete `auth.*` tables first and try to re-run already-applied migrations → GoTrue fails with `column "client_id" does not exist`, AppFlowy Cloud fails with `trigger "af_workspace_after_insert" already exists`.

**Fix:** sync both migration tables, then restart:

```bash
docker exec appflowy-db psql -U appflowy -d appflowy -c "
INSERT INTO auth.schema_migrations (version)
SELECT version FROM public.schema_migrations
WHERE version NOT IN (SELECT version FROM auth.schema_migrations);

INSERT INTO auth._sqlx_migrations (version, description, installed_on, success, checksum, execution_time)
SELECT version, description, installed_on, success, checksum, execution_time
FROM public._sqlx_migrations
WHERE version NOT IN (SELECT version FROM auth._sqlx_migrations);
"
docker restart appflowy-gotrue appflowy-cloud
```

### Full data wipe and fresh start

```bash
uv run homeserver.py prod down appflowy
sudo rm -rf ~/homeserver/service_data/data/appflowy/
docker volume rm appflowy-postgres appflowy-redis-alpine
mkdir -p ~/homeserver/service_data/data/appflowy/minio
uv run homeserver.py prod up appflowy
```

After a clean wipe, the `search_path` fix (baked into `GOTRUE_DB_DATABASE_URL` in `compose.yml`) applies automatically — everything works without manual steps.

### Stale gotrue IP after recreation

Recreating `appflowy-gotrue` alone leaves `appflowy-nginx` with a stale cached IP for it (502s on `/gotrue/*`):

```bash
docker restart appflowy-nginx
```

Run this after any `appflowy-gotrue` container recreation.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
