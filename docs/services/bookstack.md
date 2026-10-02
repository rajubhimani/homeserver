# BookStack

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Shelves/books/chapters/pages wiki — simple, dead-reliable structure. Good fit for "one book per homelab service, one page per gotcha."
**Port:** `8115` (host) → `80` (container) | **Data:** `service_data/data/bookstack/` | **Requires:** MariaDB, on the shared server ([shared-mariadb](shared-mariadb.md), started automatically)

## Setup

```bash
cp services/bookstack/.env.example services/bookstack/.env
# generate APP_KEY:
docker run --rm --entrypoint /bin/bash lscr.io/linuxserver/bookstack:v26.09.1-ls287 \
  -c "php /app/www/artisan key:generate --show"
# paste the output (including "base64:") into services/bookstack/.env as APP_KEY, set the MYSQL_* passwords
uv run homeserver.py dev up bookstack
```

## Admin account

Default credentials on first start: `admin@admin.com` / `password` — change these immediately after first login.

## Registration

No env var toggle — BookStack's self-registration is controlled entirely through the admin UI (Settings → Registration) after first login, default off until an admin enables it there.

To enable it:

1. Log in as an admin.
2. Click the gear icon (top-right) → **Settings**.
3. Left sidebar → **Registration**.
4. Toggle **Allow Registration** on.
5. Optional on the same page: require email confirmation before a new
   account can log in, restrict signup to specific email domains, and set
   the default role assigned to self-registered users.
6. Save.

New users can then sign up from the login page's "Register" link.

## Using it day to day

- **Shelves → Books → Chapters → Pages** is the hierarchy — a Shelf groups related Books, a Book contains Chapters and/or Pages directly, Chapters group Pages within a Book.
- **Page editor** supports both WYSIWYG and Markdown modes (toggle per-page) — pick once per page, not a global setting.
- **No usable Android app as of this check:** the only official Android app ("BookStack Mobile") was unpublished from Google Play back in 2022 and never replaced. An iOS-only third-party client ("BookStax") exists but has no Android counterpart. For Android, the browser at `https://bookstack.${DOMAIN}` is the only practical option — watch for "Bookstack" (a different, unrelated reading-tracker app) showing up in Play Store search instead of what you're looking for.

## Notes

- Uses the `linuxserver/bookstack` image, which follows the `PUID`/`PGID`/`/config` convention (same pattern as `syncthing` in this stack) rather than this repo's usual `DATA_ROOT` bind-mount-only shape — config, uploads, and BookStack's own `.env` all live under `service_data/data/bookstack/config/`.
- **Database:** BookStack's database lives on the shared MariaDB server (`shared-mariadb`, MariaDB 11.8), not in its own container. `homeserver.py` reads the `shared_db` entry in `services.json` (pointing at `MYSQL_DATABASE`/`MYSQL_USER`/`MYSQL_PASSWORD` in this service's `.env`), starts the server if needed, and creates the database plus a user granted on that database only. Snapshots include `bookstack_shareddb_bookstack_<ts>.sql`. Converted 2026-10-01 as the MariaDB pilot; verified with a backup → drop → restore round trip and the automatic stop once BookStack went down. (Until then it ran its own `bookstack-db` container; `MYSQL_ROOT_PASSWORD` in `.env` is now unused.)
- Health endpoint: `/status`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
