# Snappymail

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Fast, lightweight webmail client — good default for daily use.
**Port:** `8097` (host) → `8888` (container) | **Data:** `service_data/data/snappymail/`

## Setup

```bash
cp snappymail/.env.example snappymail/.env
uv run homeserver.py dev up snappymail
```

## Admin panel

`http://<ip>:8097/?admin` — set `SNAPPYMAIL_ADMIN_PASSWORD` in `.env` first.

Configure IMAP/SMTP in the admin panel: IMAP → `stalwart:143`, SMTP → `stalwart:587`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
