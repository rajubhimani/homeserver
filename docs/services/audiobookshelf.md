# Audiobookshelf

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Audiobook and podcast server with mobile app support.
**Port:** `8094` (host) → `80` (container) | **Data:** `service_data/data/audiobookshelf/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~36MB

## Setup

```bash
cp services/audiobookshelf/.env.example services/audiobookshelf/.env
# place/symlink your library under service_data/data/audiobookshelf/audiobooks/
# and .../podcasts/ — both are subdirectories of DATA_ROOT, not separate env vars
uv run homeserver.py dev up audiobookshelf
```

## First login

Browse to `http://<ip>:8094` — create the admin account on first launch. Connect the Audiobookshelf mobile app to `https://audiobookshelf.yourdomain.com`.

## Notes

- Health endpoint: `/ping`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
