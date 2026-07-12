# OpenProject

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Project management with Gantt charts, wikis, and issue tracking.
**Port:** `8099` (host) → `80` (container) | **Data:** `service_data/data/openproject/` | **Requires:** 4096MB (4GB) stated minimum per OpenProject's own docs, bundled Postgres — corrected from a previous, lower unverified figure in this doc

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

**Memory cap:** `deploy.resources.limits.memory: 3G` — **this is already below OpenProject's own stated 4GB minimum** (see top of doc, openproject.org/docs/installation-and-operations/system-requirements/). It's a backstop cap rather than internal Postgres tuning (the bundled Postgres isn't separately configurable the way a standalone `<service>-db` container's `command:` flags would be). **Measured idle usage is already 1.94GB (65% of the 3G cap) with zero users** — real risk of OOM-kill under actual multi-user load. Raise the cap to at least 4G if that happens; recreate just this container after changing it: `docker compose -f compose.yml -f compose.prod.yml up -d --no-deps openproject`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
