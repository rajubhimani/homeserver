# Ntfy

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Push notifications to phone/desktop via simple HTTP requests.
**Port:** `8092` (host) → `80` (container) | **Data:** `service_data/data/ntfy/`

## Setup

```bash
cp ntfy/.env.example ntfy/.env
uv run homeserver.py dev up ntfy
```

## Usage

Send a notification:

```bash
curl -d "Backup complete" https://ntfy.yourdomain.com/my-topic
```

Install the Ntfy app on your phone and subscribe to your topic.

## Notes

- No login by default — add `NTFY_AUTH_FILE` to enable auth
- Uses SSE streaming — nginx config includes `proxy_buffering off`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
