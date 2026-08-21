# Uptime Kuma

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Monitor services and alert when something goes down.
**Port:** `3001` (host) → `3001` (container) | **Data:** `service_data/data/uptime-kuma/` | **Requires:** MariaDB (bundled `uptime-kuma-db` container) | **Memory:** no hard limit set on the app; measured idle ~56MB — `uptime-kuma-db` capped at 384M

## Setup

```bash
cp services/uptime-kuma/.env.example services/uptime-kuma/.env
# edit MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD in .env
uv run homeserver.py dev up uptime-kuma
```

## First login

Browse to `http://<ip>:3001` — create the admin account on first launch, then add monitors for each service subdomain.

## Database

Uses external MariaDB (`uptime-kuma-db`, own container in this service's compose stack) instead of the app's default bundled SQLite, so monitor/heartbeat data lives in a named Docker volume (`uptime-kuma-mariadb`) and gets picked up automatically by this stack's `backup`/`down` snapshot system — see the `homeserver-backups` skill. Uptime Kuma's default SQLite is the officially recommended choice for a single-instance setup like this one and was already covered by the `service_data/data/uptime-kuma` bind mount; MariaDB was chosen here for consistency with the rest of the stack, not because SQLite had a backup gap. Wired via `UPTIME_KUMA_DB_TYPE=mariadb` and the `UPTIME_KUMA_DB_*` env vars in `compose.yml` (Uptime Kuma ≥2.0 required — this stack runs 2.5.0). Note: Uptime Kuma has no built-in SQLite→MariaDB migration tool — switching `UPTIME_KUMA_DB_TYPE` starts with an empty database.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
