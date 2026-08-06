# NocoDB

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Turns any database into a spreadsheet-style UI (Airtable alternative).
**Port:** `8126` (host) → `8080` (container) | **Data:** `service_data/data/nocodb/` | **Requires:** Postgres

## Setup

```bash
cp services/nocodb/.env.example services/nocodb/.env
# set POSTGRES_PASSWORD and NC_AUTH_JWT_SECRET (openssl rand -hex 24)
uv run homeserver.py dev up nocodb
```

Open `https://nocodb.<domain>/` (or `http://<host>:8126` in dev) and create the first account — it becomes the base owner.

## Registration

No env var toggle — the first account created through the UI becomes the workspace owner, further users are invited from inside the app.

## Notes

- `NC_DB` wires NocoDB's own metadata store to the `nocodb-db` Postgres container; this is separate from any external database you later connect NocoDB *to* as a data source (that's configured per-base inside the app).
- `NC_AUTH_JWT_SECRET` is set explicitly rather than left unset — NocoDB generates a random JWT secret on every restart if it's not set, which silently invalidates every active session each time the container restarts.
- Health endpoint: `/api/v1/health`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
