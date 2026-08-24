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

Browse to `http://<ip>:8094` — create the admin account on first launch.

## Connecting the Android app

Official **Audiobookshelf** app ([Google Play](https://play.google.com/store/apps/details?id=com.audiobookshelf.app)) — on first launch it shows "server not connected"; tap **Connect**, enter `https://audiobookshelf.${DOMAIN}`, then log in with the account created above. Streams audiobooks/podcasts directly, supports offline downloads.

## Notes

- Health endpoint: `/ping` (confirmed via `services/audiobookshelf/compose.yml`'s healthcheck — `wget --spider http://localhost:80/ping`, plain 200 on success)

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
