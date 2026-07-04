# Miniflux

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Minimal, fast RSS reader with keyboard shortcuts, no JavaScript frontend.
**Port:** `8093` (host) → `8080` (container) | **Data:** `service_data/miniflux/` | **Requires:** Postgres

## Setup

```bash
cp miniflux/.env.example miniflux/.env
# set ADMIN_USERNAME, ADMIN_PASSWORD, POSTGRES_PASSWORD
sh homeserver.sh dev up miniflux
```

## Admin account

Created on first start from `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`.

## Notes

- Health endpoint: `/healthcheck`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
