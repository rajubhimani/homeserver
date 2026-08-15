# Karakeep (formerly Hoarder)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted bookmark manager with AI auto-tagging and full-text search of saved pages.
**Port:** `8117` (host) → `3000` (container) | **Data:** `service_data/data/karakeep/` | **Requires:** bundled SQLite (no external DB), plus Meilisearch and a headless Chrome container

## Setup

```bash
cp services/karakeep/.env.example services/karakeep/.env
# set NEXTAUTH_SECRET and MEILI_MASTER_KEY to long random strings
uv run homeserver.py dev up karakeep
```

Open `https://karakeep.<domain>/` (or `http://<host>:8117` in dev) and register the first account.

## Registration

`DISABLE_SIGNUPS` in `.env`, default `false`. Set to `true` once your account exists to close the instance to new signups.

## Architecture — three containers

- `karakeep` — the app itself (web UI + background workers combined), SQLite database and uploaded assets under `service_data/data/karakeep/data/`.
- `karakeep-meilisearch` — full-text search index. Data lives in a named Docker volume (`karakeep-meilisearch`), not under `service_data/data/` — it's a rebuildable index, not source data.
- `karakeep-chrome` — headless Chrome (`alpine-chrome`), used for fetching/rendering pages so bookmarks get proper screenshots and content extraction.

## Notes

- AI auto-tagging is optional and off by default. This stack already runs Ollama — point Karakeep at it instead of paying for OpenAI by uncommenting the `OPENAI_BASE_URL`/`OPENAI_API_KEY`/`INFERENCE_*` block in `.env` (see the comments there). Requires `ollama` to be running (`uv run homeserver.py dev up ollama`).
- Health endpoint: `/api/health` (already baked into the image's own Dockerfile `HEALTHCHECK`; the `compose.yml` entry here just mirrors it for `docker ps`/`depends_on` visibility).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
