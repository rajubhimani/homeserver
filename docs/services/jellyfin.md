# Jellyfin

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Stream movies, TV shows, and music from your server.
**Port:** `8096` (host) → `8096` (container) | **Data:** `service_data/data/jellyfin/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~161MB — but **RAM is not the real constraint here**. Jellyfin's own docs recommend 8GB and emphasize CPU/GPU, not RAM: without hardware acceleration, CPU-only transcoding of HEVC/AV1/VP9 or HDR tone-mapping is "very performance demanding" (jellyfin.org/docs/general/administration/hardware-selection/) — idle numbers say nothing about what happens during actual transcoded playback

## Setup

```bash
cp jellyfin/.env.example jellyfin/.env
# set MEDIA_ROOT to your media drive path
uv run homeserver.py dev up jellyfin
```

## First login

Open `http://<ip>:8096` — the setup wizard creates the admin account.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
