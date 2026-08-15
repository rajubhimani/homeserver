# Uptime Kuma

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Monitor services and alert when something goes down.
**Port:** `3001` (host) → `3001` (container) | **Data:** `service_data/data/uptime-kuma/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~104MB

## Setup

```bash
cp services/uptime-kuma/.env.example services/uptime-kuma/.env
uv run homeserver.py dev up uptime-kuma
```

## First login

Browse to `http://<ip>:3001` — create the admin account on first launch, then add monitors for each service subdomain.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
