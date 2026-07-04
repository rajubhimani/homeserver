# Paperless-ngx

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Scan, OCR, and archive documents with full-text search.
**Port:** `8010` (host) → `8000` (container) | **Data:** `service_data/paperless/` | **Requires:** Postgres + Redis

## Setup

```bash
cp paperless/.env.example paperless/.env
# set POSTGRES_PASSWORD, PAPERLESS_SECRET_KEY, PAPERLESS_ADMIN_USER/PASSWORD
sh homeserver.sh dev up paperless
```

## Admin account

Auto-created from `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` on first start. To create another:

```bash
docker exec -it paperless python manage.py createsuperuser
```

## Usage notes

- Consumption folder: drop PDFs into `service_data/paperless/consume/` to auto-import
- No public signup — always admin-managed

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
