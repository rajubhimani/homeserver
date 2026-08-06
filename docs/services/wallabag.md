# Wallabag

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Read-it-later app — saves a clean, readable copy of articles for offline reading (self-hosted Pocket alternative).
**Port:** `8121` (host) → `80` (container) | **Data:** `service_data/data/wallabag/` | **Requires:** Postgres

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

This creates the schema, prompts for (and creates) the admin account, and sets up config defaults. Default credentials if you accept the prompts as-is: `wallabag` / `wallabag` — change immediately after first login.

## Registration

`SYMFONY__ENV__FOSUSER_REGISTRATION` in `.env`, default `true`. Set to `false` once accounts exist to close the instance to new signups.

## Notes

- Overlaps in purpose with Karakeep (also in this stack) — Karakeep leans toward bookmark management with AI auto-tagging and full-text search across saved pages, Wallabag leans toward "save this article, strip the clutter, read it later/offline." Both are running because they were chosen deliberately as separate tools, not because one supersedes the other — pick whichever fits a given use case, or drop one later if the overlap turns out not to matter.
- Article content and images live under `service_data/data/wallabag/data/` and `.../images/`.
- Health endpoint: `/api/info`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
