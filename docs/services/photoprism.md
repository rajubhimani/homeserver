# PhotoPrism

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** AI-powered private photo library, self-hosted.
**Port:** `8124` (host) → `2342` (container) | **Data:** `service_data/data/photoprism/` (config/cache/thumbnails) + `service_data/media/photoprism/` (the actual photo/video library) | **Requires:** MariaDB
**Tier:** manual-only — not started by `up min`/`core`/`all`, start with `uv run homeserver.py dev up photoprism`

## Why manual-only

PhotoPrism is redundant with Immich, already core in this stack — both are AI-powered self-hosted photo libraries. Immich is the default; PhotoPrism is here for its different face-recognition/tagging approach in case that's ever specifically needed, at the cost of running (and keeping in sync) a second photo library and a second MariaDB instance. Same reasoning as `gitlab` vs `forgejo` and `stirling-pdf` (full) vs `stirling-pdf-lite` elsewhere in this stack.

## Setup

```bash
cp photoprism/.env.example photoprism/.env
# set MARIADB_PASSWORD, MARIADB_ROOT_PASSWORD, and PHOTOPRISM_ADMIN_PASSWORD (min 8 chars)
uv run homeserver.py dev up photoprism
```

Open `https://photoprism.<domain>/` (or `http://<host>:8124` in dev) and log in with `PHOTOPRISM_ADMIN_USER`/`PHOTOPRISM_ADMIN_PASSWORD`.

## Registration

None — single admin account set via env vars before first start (`PHOTOPRISM_ADMIN_PASSWORD` can't be changed via env var afterward; use the `photoprism` CLI inside the container instead). No public signup concept applies.

## Notes

- **`ORIGINALS_ROOT` (the photo/video library) is deliberately outside `DATA_ROOT`**, at `service_data/media/photoprism/` — same pattern as Immich's `UPLOAD_LOCATION` and Jellyfin's `MEDIA_ROOT`. `backup_service()` tars the entire `DATA_ROOT` on every snapshot; a multi-GB+ photo library nested inside it would get fully re-archived every time.
- `photoprism-db` (MariaDB) is tuned for a single-consumer workload (`--innodb-buffer-pool-size=256M --max-connections=30`), capped at 512M via `deploy.resources.limits.memory` — see the `homeserver-postgres` skill for the general tuning approach (applies to MariaDB the same way as Postgres).
- Health endpoint: `/api/v1/status`.
- PhotoPrism recommends 4GB+ RAM and swap available for indexing — heavier than most services in this stack, another reason it isn't in a default-on tier.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
