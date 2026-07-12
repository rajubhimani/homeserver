# Audiobookshelf

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Audiobook and podcast server with mobile app support.
**Port:** `8094` (host) → `80` (container) | **Data:** `service_data/data/audiobookshelf/`

## Setup

```bash
cp audiobookshelf/.env.example audiobookshelf/.env
# set AUDIOBOOKS_PATH and PODCASTS_PATH to your media locations
uv run homeserver.py dev up audiobookshelf
```

## First login

Browse to `http://<ip>:8094` — create the admin account on first launch. Connect the Audiobookshelf mobile app to `https://audiobookshelf.yourdomain.com`.

## Notes

- Health endpoint: `/ping`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
