# Vikunja

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted to-do list and task management app — projects, due dates, labels, Kanban/Gantt views.
**Port:** `8111` (host) → `3456` (container) | **Data:** `service_data/data/vikunja/` | **Requires:** Postgres

## Setup

```bash
cp services/vikunja/.env.example services/vikunja/.env
# set POSTGRES_PASSWORD and VIKUNJA_SERVICE_SECRET to random values
uv run homeserver.py dev up vikunja
```

Vikunja ships as a single combined image (frontend + API on one port, 3456) as of the 2.x releases — there's no separate frontend/api container to wire up.

## Admin account

No admin account is created on first start. Open `https://vikunja.<domain>/` (or `http://<host>:8111` in dev) and register the first account through the UI — it becomes a regular user, not an auto-promoted admin; grant admin rights from inside the app if needed.

## Registration

`VIKUNJA_ENABLE_REGISTRATION` in `.env` (maps to `VIKUNJA_SERVICE_ENABLEREGISTRATION`) controls self-signup, default `true`. Set to `false` once accounts are provisioned to close the instance to new signups.

## Notes

- `VIKUNJA_SERVICE_SECRET` signs JWTs — keep it stable across restarts (a rotated value invalidates every existing session). It's set explicitly in `.env` rather than left to the image's random-at-startup default for this reason.
- `VIKUNJA_SERVICE_PUBLICURL` is hardcoded to `https://vikunja.${DOMAIN}/` in `compose.yml` since CORS requires it to match the public-facing URL.
- Health endpoint: `/health` (unauthenticated, returns plaintext `OK`). The container itself is a `scratch`-based image with no shell/curl/wget, so its own `compose.yml` healthcheck uses the binary's built-in `vikunja healthcheck` subcommand instead of an HTTP probe.
- File uploads (task attachments) are capped by `VIKUNJA_FILES_MAXSIZE` (default `20MB`) and stored under `service_data/data/vikunja/files/`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
