# OpenProject

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Project management with Gantt charts, wikis, and issue tracking.
**Port:** `8099` (host) → `80` (container) | **Data:** `service_data/openproject/` | **Requires:** ~2 GB RAM (bundled Postgres)

## Setup

```bash
cp openproject/.env.example openproject/.env
# generate: openssl rand -hex 64 → SECRET_KEY_BASE
sh homeserver.sh dev up openproject
```

## Default login

`admin` / `admin` — **change immediately** on first login.

## Implementation note — HTTPS behind Cloudflare

`OPENPROJECT_HTTPS` must be `"true"` when running behind Cloudflare/any TLS-terminating proxy. This is OpenProject's own documented env var for telling Rails the connection is secure, independent of the `X-Forwarded-Proto` header the proxy sends. Leaving it `"false"` while the proxy claims `https` is contradictory and causes broken links/redirect issues.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
