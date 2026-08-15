# Miniflux

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Minimal, fast RSS reader with keyboard shortcuts, no JavaScript frontend.
**Port:** `8093` (host) → `8080` (container) | **Data:** `service_data/data/miniflux/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~61MB total (app 14 + db 47)

## Setup

```bash
cp services/miniflux/.env.example services/miniflux/.env
# set ADMIN_USERNAME, ADMIN_PASSWORD, POSTGRES_PASSWORD
uv run homeserver.py dev up miniflux
```

## Admin account

Created on first start from `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`.

## Notes

- Health endpoint: `/healthcheck`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
