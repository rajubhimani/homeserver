# Wallabag

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Read-it-later app — saves a clean, readable copy of articles for offline reading (self-hosted Pocket alternative).
**Port:** `8121` (host) → `80` (container) | **Data:** `service_data/data/wallabag/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~50MB total (app 32 + db 18)

## Setup

```bash
cp services/wallabag/.env.example services/wallabag/.env
# set POSTGRES_PASSWORD and SYMFONY__ENV__SECRET
uv run homeserver.py dev up wallabag
```

**The database schema is not created automatically** — the image doesn't run `wallabag:install` on its own against Postgres. Run it once after the containers are up (the healthcheck will show `unhealthy`/`500` on `/api/info` until this is done):

```bash
docker exec -it wallabag php bin/console wallabag:install --env=prod -n
```

This creates the schema, prompts for (and creates) the admin account, and sets up config defaults. Default credentials if you accept the prompts as-is: `wallabag` / `wallabag` — **change immediately after first login**:

1. Log in at `https://wallabag.<domain>/` with `wallabag` / `wallabag`.
2. Go to **Settings → Password** tab.
3. Set a strong password there and save.

There is no CLI or env-var way to set this directly during install — this
version's console only ships `wallabag:user:list`/`wallabag:user:show`, no
`user:create` or password-reset command (checked via `php bin/console list
wallabag --env=prod` inside the container) — so the web UI's Settings page
is the only supported way to change it, and it should be the first thing
you do after the install step above, before leaving the instance
reachable with the default credentials.

**Running the installer leaves `/api/info` still 500ing afterward**: `docker exec` runs as `root` by default, but the actual request-handling process is `php-fpm`'s `www` pool running as `nobody` (`nginx` serves static assets as its own `nginx` user, unrelated). The installer writes fresh cache files under `var/cache/prod/` as `root`, which `nobody` then can't write to on the next request — surfaces as `The directory ".../jms_serializer_default" is not writable` in `var/logs/prod.log`. Fix once, after running the installer:

```bash
docker exec wallabag chown -R nobody:nobody /var/www/wallabag/var
```

## Registration

`SYMFONY__ENV__FOSUSER_REGISTRATION` in `.env`, default `true`. Set to `false` once accounts exist to close the instance to new signups.

## Notes

- Overlaps in purpose with Karakeep (also in this stack) — Karakeep leans toward bookmark management with AI auto-tagging and full-text search across saved pages, Wallabag leans toward "save this article, strip the clutter, read it later/offline." Both are running because they were chosen deliberately as separate tools, not because one supersedes the other — pick whichever fits a given use case, or drop one later if the overlap turns out not to matter.
- Article content and images live under `service_data/data/wallabag/data/` and `.../images/`.
- Health endpoint: `/api/info`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
