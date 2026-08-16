# Paperless-ngx

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Scan, OCR, and archive documents with full-text search.
**Port:** `8010` (host) → `8000` (container) | **Data:** `service_data/data/paperless/` | **Requires:** Postgres + Redis | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~582MB total (app 521 + db 53 + redis 8) — closely matches community-reported idle figures (~600-900MB). **OCR ingestion of scanned documents spikes this to 1.5-2GB + 100% CPU on one core**, not reflected in the idle number

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

## Usage notes

- Consumption folder: drop PDFs into `service_data/data/paperless/app/consume/` to auto-import
- No public signup — always admin-managed

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
