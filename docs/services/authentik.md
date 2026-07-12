# Authentik

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Identity provider — SSO, OAuth2, OIDC, SAML for all your other services.
**Port:** `8088` (host) → `9000` (container, `authentik-server`) | **Data:** `service_data/data/authentik/` | **Requires:** Postgres + Redis

## Setup

```bash
cp authentik/.env.example authentik/.env
# generate: openssl rand -hex 32 → AUTHENTIK_SECRET_KEY
# set POSTGRES_PASSWORD
uv run homeserver.py dev up authentik
```

`AUTHENTIK_SECRET_KEY` must be set **before** first start.

## First login

Browse to `http://<ip>:8088/if/admin/` — set the password for the default admin account `akadmin`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
