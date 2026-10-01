# Paperless-ngx

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Scan, OCR, and archive documents with full-text search.
**Port:** `8010` (host) → `8000` (container) | **Data:** `service_data/data/paperless/` | **Requires:** Postgres + Redis | **Memory:** database on `shared-postgres` (counted there); app: no hard limit set; measured idle ~582MB total (app 521 + db 53 + redis 8), measured before the 2026-10-01 move to the shared server — closely matches community-reported idle figures (~600-900MB). **OCR ingestion of scanned documents spikes this to 1.5-2GB + 100% CPU on one core**, not reflected in the idle number

**Database:** on the shared Postgres server ([shared-postgres](shared-postgres.md)), not its own container — since 2026-10-01. `homeserver.py` starts `shared-postgres` before this service and creates its database and login from `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` in `services/paperless/.env` (the `shared_db` entry in `services.json`); snapshots include a dump of just this service's database.


## Setup

```bash
cp services/paperless/.env.example services/paperless/.env
# set POSTGRES_PASSWORD, PAPERLESS_SECRET_KEY, PAPERLESS_ADMIN_USER/PASSWORD
uv run homeserver.py dev up paperless
```

## Admin account

Auto-created from `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` on first start. To create another:

```bash
docker exec -it paperless python manage.py createsuperuser
```

## Connecting the Android app

**Paperless Mobile** ([F-Droid](https://f-droid.org/packages/de.astubenbord.paperless_mobile/) or Google Play), by community developer astubenbord, is the commonly used unofficial Android client — there's no official first-party mobile app. On first launch, enter the server URL `https://paperless.${DOMAIN}` and log in with the same account created above; it authenticates via the same Django user account (bearer token fetched at login, not a separate API-key setup step). Requires the login user to have `Users → View` and `UISettings → View` permissions — the default admin account already has both.

## Using it day to day

- **Consumption folder:** drop PDFs into `service_data/data/paperless/app/consume/` to auto-import — this is the main non-UI ingestion path (e.g. a scanner that saves directly to a watched network folder).
- **Uploading from the web UI or mobile app:** both support direct upload/photo capture in addition to the consumption folder.
- **Tags/correspondents/document types** are the three main ways to organize documents for search — set them per-document (manually or via auto-detection rules) rather than relying on folder structure, since Paperless is flat-storage-plus-metadata, not folder-based.

## Health endpoint

No explicit `healthcheck:` block for the main `paperless` container in `services/paperless/compose.yml` (only the `paperless-db`/`paperless-redis` sidecars have one) — but the upstream image bakes its own `HEALTHCHECK` into the Dockerfile (a `curl` against the local webserver), so `docker inspect paperless` still reports a health status even without an explicit override here.

## Usage notes

- No public signup — always admin-managed

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
