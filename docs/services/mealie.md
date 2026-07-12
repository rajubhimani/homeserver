# Mealie

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Recipe manager and meal planner.
**Port:** `9925` (host) → `9000` (container) | **Data:** `service_data/data/mealie/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~329MB total (app 278 + db 51)

## Setup

```bash
cp mealie/.env.example mealie/.env
# set POSTGRES_PASSWORD
uv run homeserver.py dev up mealie
```

## Default credentials

`changeme@example.com` / `MyPassword` — **change immediately**.

## Registration

Disabled by default (`ALLOW_SIGNUP=false`).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
