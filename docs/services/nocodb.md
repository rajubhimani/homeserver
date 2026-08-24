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

## Using it day to day

No mobile app — a third-party prototype client exists on GitHub but isn't published to Google Play/App Store, so `https://nocodb.${DOMAIN}` in a browser is the only practical way in, on any platform.

- **Bases** are the top-level workspace unit — each connects to one or more data sources (its own bundled Postgres-backed store by default, or an external database/API added under a base's **Data Sources** tab) and holds tables, views, and automations together.
- **Import from Airtable** or create a table from scratch — both are options when creating a new base.
- **Views** (Grid/Gallery/Kanban/Form/Calendar) are saved per-table, multiple views over the same underlying data, useful for giving different people a different lens on the same table without duplicating it.

## Notes

- `NC_DB` wires NocoDB's own metadata store to the `nocodb-db` Postgres container; this is separate from any external database you later connect NocoDB *to* as a data source (that's configured per-base inside the app).
- `NC_AUTH_JWT_SECRET` is set explicitly rather than left unset — NocoDB generates a random JWT secret on every restart if it's not set, which silently invalidates every active session each time the container restarts.
- Health endpoint: `/api/v1/health`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
