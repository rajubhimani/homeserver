# Excalidraw

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Hand-drawn-style whiteboard for diagrams and sketches — doesn't look like a corporate slide.
**Port:** `8116` (host) → `80` (container) | **Data:** none | **Requires:** nothing

## Setup

```bash
cp services/excalidraw/.env.example services/excalidraw/.env   # no values to fill in — see below
uv run homeserver.py dev up excalidraw
```

Open `https://excalidraw.<domain>/` (or `http://<host>:8116` in dev).

## Important limitation: no server-side persistence or self-hosted collaboration

The official `excalidraw/excalidraw` image is **just the static frontend** — a pre-built JS app served by nginx. There's no database, no `DATA_ROOT`, and nothing in `service_data/` for this service:

- **Drawings are saved only in the browser's own localStorage/IndexedDB.** Clearing browser data, switching browsers, or switching devices loses the drawing — there's no server-side save.
- **The real-time collaboration ("Live collaboration") button in the UI points at Excalidraw's own public `oss-collab.excalidraw.com` server**, not anything self-hosted here — the collab server URL is compiled into the JS bundle at build time and can't be changed with an env var. Fully self-hosting collaboration (an `excalidraw-room` websocket relay + a storage backend) requires building a custom image or patching the bundle at container startup — a genuinely fragile, unofficial hack — so it was deliberately left out of this setup. Use the export/import (`.excalidraw` file) feature for saving and sharing work instead.

## Notes

- No health/status endpoint beyond `/` itself (static file serving) — the compose healthcheck just checks the page loads.
- No env vars, no registration, no accounts — nothing to configure beyond starting the container.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
