# Cal.com

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted scheduling and booking pages (Calendly alternative).
**Port:** `8129` (host) → `3000` (container) | **Data:** none beyond Postgres — the app itself is stateless | **Requires:** Postgres

## Setup

```bash
cp calcom/.env.example calcom/.env
# set POSTGRES_PASSWORD, NEXTAUTH_SECRET (openssl rand -base64 32),
# CALENDSO_ENCRYPTION_KEY (openssl rand -base64 24)
uv run homeserver.py dev up calcom
```

Open `https://calcom.<domain>/` (or `http://<host>:8129` in dev) and create the first account.

## Registration

Self-registration is on by default through the UI.

## Notes

- `CALENDSO_ENCRYPTION_KEY` encrypts every stored integration credential (Google OAuth tokens, calendar connections). **Never change it after first run** — doing so permanently corrupts everything it encrypted.
- SMTP (`EMAIL_*` vars) is required for actually sending booking confirmations/reminders — fill those in for real use.
- The official upstream `docker-compose.yaml` also wires up a separate API v2 container, Redis, and an optional Prisma Studio service (for building from source / advanced API use) — deliberately left out here to keep this a normal single-app-plus-DB service like everything else in this stack. Revisit only if the v2 API is specifically needed.
- Health endpoint: `/auth/login` — `/api/health` doesn't exist on this version (404); the root `/` redirects (307) to `/auth/login` for unauthenticated requests, so the compose healthcheck and landing-page health route both hit that page directly instead.
- The app logs a repeating `Match of WEBAPP_URL with ALLOWED_HOSTNAMES failed` warning (an organization-domain feature check) — harmless, and deliberately left unset here. Cal.com expects `ALLOWED_HOSTNAMES` as an already-JSON-quoted value (e.g. `"calcom.example.com"`, not a bare string) since it wraps it in `[...]` and parses the result as JSON; a plain unquoted value causes a hard `SyntaxError` crash (confirmed while testing this setup), which is worse than the warning it was meant to silence. Not set here for that reason — revisit only with the exact quoting the app expects if the warning becomes a real problem.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
