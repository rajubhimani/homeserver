# Penpot

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted design and prototyping tool (Figma alternative), real-time collaborative.
**Port:** `8131` (host) → `8080` (container, on `penpot-frontend`) | **Data:** `service_data/data/penpot/assets/` | **Requires:** Postgres, Redis (Valkey)

## Setup

```bash
cp services/penpot/.env.example services/penpot/.env
# set POSTGRES_PASSWORD and PENPOT_SECRET_KEY (python3 -c "import secrets; print(secrets.token_urlsafe(64))")
uv run homeserver.py dev up penpot
```

Open `https://penpot.<domain>/` (or `http://<host>:8131` in dev) and create the first account.

## Registration

Self-registration is on by default. Add `disable-registration` to `PENPOT_FLAGS` in `.env` once accounts exist to close it — officially described as recommended for demo instances rather than hardened production use, but reasonable for a personal instance.

## Architecture — 5 containers

- `penpot-db` (Postgres) — app metadata.
- `penpot-redis` (Valkey) — websocket notifications/caching.
- `penpot-backend` — API server, handles asset storage (`assets-fs` backend, writes to the shared `assets` volume).
- `penpot-exporter` — headless-browser-based PDF/PNG export, talks to the frontend internally.
- `penpot-frontend` — the actual web UI + reverse-proxies to backend/exporter internally; this is what `nginx-plain` and the landing-page health check point at.

Two services from the official upstream compose are deliberately **not** included: `penpot-mcp` (Model Context Protocol server for AI tool integration — opt-in, not needed for normal use) and `penpot-mailcatch` (a dev-only SMTP-catching tool for testing emails without a real mail server — replaced here by real `PENPOT_SMTP_*` settings in `.env`).

## Using it day to day

No confirmed official mobile app as of this check (a mobile app has been a long-standing community feature request, not something shipped) — `https://penpot.${DOMAIN}` in a browser is the primary way in on any platform. A community plugin, **Mockup Mirror**, pairs with a companion Android app to preview a design live on a physical device during design work, if that specific workflow is wanted.

- **Teams → Projects → Files** is the hierarchy — a Team is the collaboration boundary (who can see what), Projects group related Files within a team.
- **Real-time collaborative editing** — multiple people editing the same file see each other's cursors/selections live.
- **Components and design tokens** let a reusable element (a button, a color) update everywhere it's used from one edit, same concept as Figma's components.
- **Export/prototyping**: `penpot-exporter` (a separate container in this stack) handles PDF/PNG export and prototype-flow rendering — if exports fail while everything else works, check that container specifically (see "Architecture" above, it needs `PENPOT_SECRET_KEY` set too).

## Notes

- `PENPOT_SECRET_KEY` derives every other internal key — losing or changing it invalidates every active session and pending invitation. **Both `penpot-backend` and `penpot-exporter` need it set**, not just the backend — the exporter crash-loops with a `missing-key :secret-key` schema error otherwise (confirmed while verifying this setup).
- SMTP (`PENPOT_SMTP_*`) is required for invitations/notifications to actually send, but setting the host/port/credentials alone does nothing — Penpot only turns SMTP on via the `enable-smtp` flag in `PENPOT_FLAGS`, not a separate on/off env var. (An earlier version of this file had an inert `PENPOT_SMTP_ENABLED` var that Penpot never reads — caught and removed while backfilling this doc.)
- No confirmed dedicated health endpoint on the frontend — the compose healthcheck and landing-page health route both just check that `/` responds (Penpot's own backend health endpoint isn't exposed through the frontend/nginx layer, only on direct backend access).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
