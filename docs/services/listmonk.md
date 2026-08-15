# Listmonk

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted newsletter and mailing list manager — single Go binary, Postgres-backed.
**Port:** `8127` (host) → `9000` (container) | **Data:** `service_data/data/listmonk/` | **Requires:** Postgres

## Setup

```bash
cp services/listmonk/.env.example services/listmonk/.env
# set POSTGRES_PASSWORD and LISTMONK_ADMIN_PASSWORD
uv run homeserver.py dev up listmonk
```

Open `https://listmonk.<domain>/` (or `http://<host>:8127` in dev) and log in with `LISTMONK_ADMIN_USER`/`LISTMONK_ADMIN_PASSWORD`.

## Registration

No public signup — the super admin account is created automatically on first start from the `LISTMONK_ADMIN_USER`/`LISTMONK_ADMIN_PASSWORD` env vars; further users are added from inside the app.

## Notes

- The container's `command:` runs `--install --idempotent`, then `--upgrade`, then starts the server, every time it starts — this is the officially documented pattern (safe to repeat; install/upgrade are no-ops once already applied) rather than a one-time manual step like Wallabag needs.
- Uploaded media (campaign images etc.) lives under `service_data/data/listmonk/uploads/`.
- Health endpoint: `/` — `/api/health` returns `403 Forbidden` on a plain unauthenticated request (likely an Origin/Referer check on API routes), so the compose healthcheck and landing-page health route both just check the root page loads instead.
- SMTP isn't configured out of the box — set it up from inside the app (Settings → SMTP) before sending real campaigns.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
