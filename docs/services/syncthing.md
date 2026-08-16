# Syncthing

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Peer-to-peer file sync between devices, no cloud required.
**Port:** `8087` (host) → `8384` (container, web UI) — also publishes `22000/tcp`, `22000/udp`, `21027/udp` (device sync + LAN discovery) on all interfaces in both dev and prod, since peer connectivity needs to be reachable regardless of env | **Data:** `service_data/data/syncthing/data/` (your actual synced files — still Explorer-browsable) + named volume `syncthing-config` (Syncthing's own app settings, not your files — moved off the bind mount since nothing needs to browse it directly) | **Requires:** — | **Memory:** no hard limit set; measured idle ~45MB

## Setup

```bash
cp services/syncthing/.env.example services/syncthing/.env
uv run homeserver.py dev up syncthing
```

## First login

Browse to `http://<ip>:8087` — set a password immediately in Settings → GUI. Add remote devices by sharing Device IDs, then add folders to sync.

## Notes

- No central server — pure peer-to-peer
- Health endpoint: `/rest/noauth/health`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
