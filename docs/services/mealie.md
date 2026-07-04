# Mealie

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Recipe manager and meal planner.
**Port:** `9925` (host) → `9000` (container) | **Data:** `service_data/mealie/` | **Requires:** Postgres

## Setup

```bash
cp mealie/.env.example mealie/.env
# set POSTGRES_PASSWORD
sh homeserver.sh dev up mealie
```

## Default credentials

`changeme@example.com` / `MyPassword` — **change immediately**.

## Registration

Disabled by default (`ALLOW_SIGNUP=false`).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
