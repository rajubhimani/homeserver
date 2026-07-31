# Outline

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Polished self-hosted team wiki / docs app with good search.
**Port:** `8114` (host) → `3000` (container) | **Data:** `service_data/data/outline/` | **Requires:** Postgres, Redis, and an OIDC/OAuth provider (no built-in email/password login)

## Setup — Authentik OIDC required before first login

Outline has **no built-in username/password login** — it requires at least one OAuth/OIDC provider configured or nobody can sign in. This stack already runs Authentik, so use it:

1. Start Authentik first if it isn't already running: `uv run homeserver.py dev up authentik`.
2. In Authentik: create an **OAuth2/OIDC Provider**, then a matching **Application**, for Outline.
   - Redirect URI: `https://outline.<domain>/auth/oidc.callback`
3. Copy the client ID/secret and the provider's authorize/token/userinfo URLs into `outline/.env` (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_AUTH_URI`, `OIDC_TOKEN_URI`, `OIDC_USERINFO_URI`).
4. Then:

```bash
cp outline/.env.example outline/.env
# set POSTGRES_PASSWORD, SECRET_KEY, UTILS_SECRET (openssl rand -hex 32), and the OIDC_* vars from step 2-3
uv run homeserver.py dev up outline
```

Open `https://outline.<domain>/` (or `http://<host>:8114` in dev) and log in via the "Authentik" OIDC option.

## Notes

- `SECRET_KEY` / `UTILS_SECRET` must each be a random 32-byte hex string (`openssl rand -hex 32`) — Outline refuses to start without them set to non-default values.
- File attachments use `FILE_STORAGE=local`, stored under `service_data/data/outline/data/`. `FILE_STORAGE_UPLOAD_MAX_SIZE` caps uploads (default ~250MB).
- Health endpoint: `/_health`.
- Needs both Postgres and Redis — two extra containers (`outline-db`, `outline-redis`) beyond the app itself, heavier than most services in this stack.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
