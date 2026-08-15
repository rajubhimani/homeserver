# BookStack

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Shelves/books/chapters/pages wiki — simple, dead-reliable structure. Good fit for "one book per homelab service, one page per gotcha."
**Port:** `8115` (host) → `80` (container) | **Data:** `service_data/data/bookstack/` | **Requires:** MariaDB

## Setup

```bash
cp services/bookstack/.env.example services/bookstack/.env
# generate APP_KEY:
docker run --rm --entrypoint /bin/bash lscr.io/linuxserver/bookstack:v26.05.3-ls277 \
  -c "php /app/www/artisan key:generate --show"
# paste the output (including "base64:") into services/bookstack/.env as APP_KEY, set the MYSQL_* passwords
uv run homeserver.py dev up bookstack
```

## Admin account

Default credentials on first start: `admin@admin.com` / `password` — change these immediately after first login.

## Registration

No env var toggle — BookStack's self-registration is controlled entirely through the admin UI (Settings → Registration) after first login, default off until an admin enables it there.

## Notes

- Uses the `linuxserver/bookstack` image, which follows the `PUID`/`PGID`/`/config` convention (same pattern as `syncthing` in this stack) rather than this repo's usual `DATA_ROOT` bind-mount-only shape — config, uploads, and BookStack's own `.env` all live under `service_data/data/bookstack/config/`.
- `bookstack-db` uses `mariadb:11.8.8` — the first MariaDB (rather than Postgres) instance in this stack; see the `homeserver-postgres` skill for why DB data still needs a named volume (`bookstack-mariadb`, mounted at `/var/lib/mysql`) rather than a bind mount.
- Health endpoint: `/status`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
