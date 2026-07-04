# Uptime Kuma

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Monitor services and alert when something goes down.
**Port:** `3001` (host) → `3001` (container) | **Data:** `service_data/uptime-kuma/`

## Setup

```bash
cp uptime-kuma/.env.example uptime-kuma/.env
sh homeserver.sh dev up uptime-kuma
```

## First login

Browse to `http://<ip>:3001` — create the admin account on first launch, then add monitors for each service subdomain.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
