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

## Reverse proxy: no buffering (2026-10-11)

The `audiobookshelf` block in `services/nginx-plain/templates/default.conf.template` sets `proxy_buffering off;` and `proxy_request_buffering off;`. Long audio files with seeking were buffered to disk by nginx-plain before reaching the client. Same fix as Jellyfin's playback hangs (see [jellyfin.md](jellyfin.md)). Apply with `docker restart nginx-plain`, since the template is rendered at container start.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
