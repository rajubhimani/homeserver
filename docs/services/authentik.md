# Authentik

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Identity provider — SSO, OAuth2, OIDC, SAML for all your other services.
**Port:** `8088` (host) → `9000` (container, `authentik-server`, HTTP) and `9444` (host) → `9443` (container, HTTPS) | **Data:** `service_data/data/authentik/` | **Requires:** Postgres (no Redis in this compose.yml — this doc previously claimed one that doesn't exist here) | **Memory:** DB capped 384M in compose.yml; server/worker: no hard limit set; measured idle ~244MB total (server 143 + worker 49 + db 52). Authentik's own docs state a 2GB/2-core minimum for the whole stack — comfortable headroom for personal-scale use, though their GitHub issue #21413 notes real deployments at ~1400 users saw the worker alone peak past 7GB

## Setup

```bash
cp services/authentik/.env.example services/authentik/.env
# generate: openssl rand -base64 60 → AUTHENTIK_SECRET_KEY
# set POSTGRES_PASSWORD
uv run homeserver.py dev up authentik
```

`AUTHENTIK_SECRET_KEY` must be set **before** first start.

## First login

Browse to `http://<ip>:8088/if/admin/` — set the password for the default admin account `akadmin`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
