# Jellyfin

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Stream movies, TV shows, and music from your server.
**Port:** `8096` (host) → `8096` (container) | **Data:** `service_data/data/jellyfin/`

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
