# Excalidraw

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Hand-drawn-style whiteboard for diagrams and sketches — doesn't look like a corporate slide.
**Port:** `8116` (host) → `80` (container) | **Data:** none | **Requires:** nothing | **Memory:** no hard limit set; measured idle ~10MB

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
- **The top-right "Share" link button is the same story** — it uploads the scene to `json.excalidraw.com` (a separate backend from the collab server, but still one of theirs) to generate a short link. It also silently depends on infrastructure this deployment doesn't run, so treat it the same as Live Collaboration: don't expect it to actually work.

## Using it day to day — sharing without the backend features

Since both backend-dependent buttons above are non-functional here, the only sharing paths that actually work self-hosted are entirely client-side (no server round-trip at all):

- **Save/reopen a drawing:** hamburger menu → **Save to...** exports a `.excalidraw` JSON file; **Open** loads one back in. This is the closest thing to "persistence" this deployment has, since nothing is saved server-side (see above).
- **Share an editable drawing as an image:** hamburger menu → **Export image**, enable **"Embed scene"**, export as PNG or SVG. The full drawing data is embedded inside the image file itself — anyone can later drag that PNG/SVG back into their own Excalidraw (this instance or `excalidraw.com`) and continue editing it, with no server storage involved either way. This is the practical substitute for "Share" here.
- Plain PNG/SVG export (Embed scene left off) works too, for a normal non-editable image to paste elsewhere.

## Notes

- No health/status endpoint beyond `/` itself (static file serving) — the compose healthcheck just checks the page loads.
- No env vars, no registration, no accounts — nothing to configure beyond starting the container.
- **Gated behind Authentik forward-auth** — since Excalidraw has no login of its own, `excalidraw.${DOMAIN}` requires an Authentik login at the nginx layer before any request reaches the container. See [Forward-auth for other services](authentik.md#forward-auth-for-other-services-nginx-auth_request) in `authentik.md`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
