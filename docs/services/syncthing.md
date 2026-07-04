# Syncthing

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Peer-to-peer file sync between devices, no cloud required.
**Port:** `8087` (host) → `8384` (container) | **Data:** `service_data/syncthing/`

## Setup

```bash
cp syncthing/.env.example syncthing/.env
sh homeserver.sh dev up syncthing
```

## First login

Browse to `http://<ip>:8087` — set a password immediately in Settings → GUI. Add remote devices by sharing Device IDs, then add folders to sync.

## Notes

- No central server — pure peer-to-peer
- Health endpoint: `/rest/noauth/health`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
