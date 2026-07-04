# Roundcube

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Full-featured webmail with plugins, address book, and calendar.
**Port:** `8098` (host) → `80` (container) | **Data:** `service_data/roundcube/`

## Setup

```bash
cp roundcube/.env.example roundcube/.env
# set ROUNDCUBEMAIL_DEFAULT_HOST=stalwart, ROUNDCUBEMAIL_SMTP_SERVER=stalwart
sh homeserver.sh dev up roundcube
```

## Login

Use your IMAP credentials — no separate admin account, all config lives in `.env`. Admin/settings UI is at `/roundcubemail/?_task=settings`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
