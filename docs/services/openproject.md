# OpenProject

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Project management with Gantt charts, wikis, and issue tracking.
**Port:** `8099` (host) → `80` (container) | **Data:** `service_data/data/openproject/` | **Requires:** ~2 GB RAM (bundled Postgres)

## Setup

```bash
cp openproject/.env.example openproject/.env
# generate: openssl rand -hex 64 → SECRET_KEY_BASE
uv run homeserver.py dev up openproject
```

## Default login

`admin` / `admin` — **change immediately** on first login.

## Implementation note — HTTPS behind Cloudflare

`OPENPROJECT_HTTPS` must be `"true"` when running behind Cloudflare/any TLS-terminating proxy. This is OpenProject's own documented env var for telling Rails the connection is secure, independent of the `X-Forwarded-Proto` header the proxy sends. Leaving it `"false"` while the proxy claims `https` is contradictory and causes broken links/redirect issues.

## Implementation note — bundled Postgres

The single `openproject` container runs its own internal Postgres rather than using a separate `openproject-db` container like most other services in this stack. Its data lives in the named volume `openproject-pgdata` (`/var/openproject/pgdata`), which already follows the same named-volume-not-bind-mount rule as a standalone DB container, for the same reason (see the `homeserver-postgres` skill).

**Memory cap:** `deploy.resources.limits.memory: 3G` — set above the ~2 GB quoted at the top of this doc to leave headroom, since it's a backstop cap rather than internal Postgres tuning (the bundled Postgres isn't separately configurable the way a standalone `<service>-db` container's `command:` flags would be). Raise it if the container gets OOM-killed under real load; recreate just this container after changing it: `docker compose -f compose.yml -f compose.prod.yml up -d --no-deps openproject`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
