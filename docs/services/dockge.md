# Dockge

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Docker Compose stack manager UI.
**Port:** `5001` | **Data:** `service_data/data/dockge/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~132MB

## Setup

```bash
cp services/dockge/.env.example services/dockge/.env
# set DOCKGE_STACKS_DIR to an absolute path and mkdir -p it before starting
uv run homeserver.py dev up dockge
```

## Using it day to day

Confirmed against Dockge's own current docs/GitHub for the pinned `1.5.0`:

- **Create a new stack:** **+ Compose** → paste a `docker-compose.yml` directly into the editor (or paste a `docker run ...` command — Dockge converts it into a compose file automatically) → **Deploy**. Pull/up/down progress and terminal output stream live into the same screen, no page refresh.
- **Import an existing stack:** any folder with a `compose.yaml`/`docker-compose.yml` placed directly under `DOCKGE_STACKS_DIR` shows up in Dockge automatically — it's file-based, not a database, so a stack stays fully manageable from the CLI too. This is a **directory-location** distinction, not "who created it": a compose file has to actually live under `DOCKGE_STACKS_DIR` to appear here.
- **This stack's own services (managed by `homeserver.py`) live under `services/<name>/`, not `DOCKGE_STACKS_DIR`** — so they never show up in Dockge regardless of anything else; that's by design, not a limitation to work around. Use Portainer (already in this stack) to inspect/manage those containers instead — see [portainer.md](portainer.md).
- **Interactive terminal** — each stack has a shell into its own containers built into the UI, no separate `docker exec` needed.

## Health endpoint

No `healthcheck:` is defined in `services/dockge/compose.yml` — `docker ps` will always show it without a health status, and there's no dedicated endpoint documented upstream to add one against.

## Notes

- `DOCKGE_STACKS_DIR` must be an absolute path — relative paths silently break stack management

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
