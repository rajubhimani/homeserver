# Supabase

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted Firebase alternative — Postgres database, auth, auto-generated REST/GraphQL API, realtime subscriptions, file storage, and edge functions in one platform.
**Port:** `8133` (host) → `8000` (container, Kong API gateway) | **Data:** `service_data/data/supabase/` + named volumes | **Requires:** nothing external — bundles its own Postgres

## The heaviest service in this stack

12 containers: `supabase-db` (Postgres), `supabase-auth` (GoTrue), `supabase-rest` (PostgREST), `supabase-realtime`, `supabase-storage`, `supabase-imgproxy`, `supabase-meta` (schema API used by Studio), `supabase-functions` (Deno edge runtime), `supabase-studio` (dashboard), `supabase-kong` (API gateway — the single entry point everything else sits behind), `supabase-pooler` (Supavisor, connection pooling). This is genuinely on the same scale as running a small platform, not a single app — expect noticeably higher combined memory/CPU than anything else in this stack.

## Setup

The upstream project vendors several non-trivial config files (Kong's declarative routing config + entrypoint script, and 7 Postgres init SQL scripts) that this service's `compose.yml` depends on directly — they're copied verbatim into `supabase/volumes/` from the official `supabase/supabase` repo (`docker/volumes/`), not reproduced by hand, to avoid subtly breaking Kong's routing rules or Postgres's role/JWT setup.

```bash
cp supabase/.env.example supabase/.env
# generate real secrets — see the long comment block at the top of .env.example,
# or run the copied official helper: bash supabase/generate-keys.sh
uv run homeserver.py dev up supabase
```

Open `https://supabase.<domain>/` (or `http://<host>:8133` in dev). The root path is Studio's dashboard, gated by `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` (HTTP basic auth, enforced by Kong) — not open self-registration like most services here. API access (REST/GraphQL/Auth/Storage/Realtime) uses the `ANON_KEY`/`SERVICE_ROLE_KEY` JWTs instead.

## Registration

There's no end-user "registration" concept at the platform level — `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` gate the Studio dashboard (effectively single-admin), while `DISABLE_SIGNUP` in `.env` controls whether **your own app's end users** can sign up through Supabase Auth (default `false` — open, since that's normal for a backend platform whose whole job is serving your application's users).

## Architecture — why so many pieces

- **`supabase-kong`** is the single public entry point; every other service is internal-only and reached exclusively through Kong's declarative routing (`volumes/api/kong.yml`), which maps public paths (`/auth/v1/*`, `/rest/v1/*`, `/storage/v1/*`, `/realtime/v1/*`, `/functions/v1/*`, `/pg/*`, `/` for Studio) to the right internal container.
- **`supabase-db`** uses the custom `supabase/postgres` image (not vanilla `postgres`) — it bundles roles, extensions (`pg_net`, etc.), and schemas (`_realtime`, `_analytics`, `_supavisor`) that the 7 mounted init scripts (`roles.sql`, `jwt.sql`, `realtime.sql`, `webhooks.sql`, `_supabase.sql`, `logs.sql`, `pooler.sql`) set up on first start. DB data lives in the named volume `supabase-db-data` (never a bind mount — see the `homeserver-postgres` skill for why), not the vendored `volumes/db/` directory upstream's own instructions bind-mount to.
- **`supabase-pooler`** (Supavisor) is Supabase's connection pooler — most client libraries are meant to connect through it, not directly to `supabase-db`.
- **`supabase-realtime`**'s container name (`realtime-dev.supabase-realtime`) looks wrong but is required verbatim — Realtime parses its own hostname to determine its tenant ID.
- File uploads live under `service_data/data/supabase/storage/`, shared between `supabase-storage` and `supabase-imgproxy` (which generates transformed/resized variants on demand).

## Notes

- Every secret in `.env` (`JWT_SECRET`, `ANON_KEY`/`SERVICE_ROLE_KEY`, `SECRET_KEY_BASE`, `VAULT_ENC_KEY`, etc.) is a one-time value — `ANON_KEY`/`SERVICE_ROLE_KEY` are JWTs *signed with* `JWT_SECRET`, so if you ever rotate `JWT_SECRET` you must re-sign both keys to match (the copied `generate-keys.sh` does this correctly; don't just change `JWT_SECRET` alone).
- Health check: Kong's root path requires HTTP basic auth and returns `401` for an unauthenticated request — that's expected and still counts as "online" for this stack's landing-page health check (any status under 500 does), not a sign of misconfiguration.
- `POSTGRES_DB=postgres` **must** be set in `.env` — several services (`supabase-auth`, `supabase-rest`, `supabase-pooler`) build their own Postgres connection strings by directly interpolating `${POSTGRES_DB}`, so an unset value silently produces a connection string with an empty database name and every one of them fails to connect (confirmed while verifying this setup — easy to miss since upstream's own compose only sets it via `.env`, not a hardcoded default in `compose.yml`).
- `supabase-storage`'s healthcheck must target `127.0.0.1`, not `localhost` — its Node process only binds IPv4 addresses, so `localhost` resolving to `::1` first causes a connection-refused loop even though the app itself is running fine (the same IPv6 pitfall that hit several other services in this stack — see `trilium`, `atuin`, etc.).
- `docker-compose.s3.yml`, `docker-compose.caddy.yml`/`docker-compose.nginx.yml` (external TLS proxy), and the Logflare/Vector analytics stack from the official repo are **not** included here — S3-backed storage, Caddy/Nginx TLS termination, and the analytics/logging pipeline are all optional add-ons layered on top of the base compose upstream, and `nginx-plain` already handles this stack's TLS/routing.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
