# Vaultwarden

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted password manager (Bitwarden-compatible).
**Port:** `8200` (host) → `80` (container) | **Data:** `service_data/data/vaultwarden/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~14MB

## Setup

```bash
cp services/vaultwarden/.env.example services/vaultwarden/.env
# set ADMIN_TOKEN (openssl rand -base64 48)
uv run homeserver.py dev up vaultwarden
```

## Admin panel

`http://<ip>:8200/admin` → enter `ADMIN_TOKEN`.

## Registration

`.env.example` ships with `SIGNUPS_ALLOWED=true` (self-signup enabled) — set it to `false` to invite-only via the admin panel → Users → Invite instead.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
