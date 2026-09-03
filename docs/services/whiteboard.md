# Nextcloud Whiteboard

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Real-time collaborative infinite-canvas whiteboard, built into [Nextcloud](nextcloud.md). This is the standalone backend server (`whiteboard` container) that Nextcloud's `whiteboard` app connects to for live collaboration — not a destination on its own, see "What `whiteboard.${DOMAIN}` actually is" below.
**Port:** `8151` (host) → `3002` (container) | **Data:** none — in-memory session storage only, nothing persisted, nothing to back up | **Requires:** nothing — self-contained | **Memory:** measured idle, no active boards: **~110MB**.
**Pinned version:** `ghcr.io/nextcloud-releases/whiteboard:v1.5.9`. Originally floated on `:stable` (upstream's own documented production tag — no clean numbered release tags existed at the time this service was first added, GHCR listing was a mix of beta/daily/commit-hash tags). Numbered tags exist now; pinned to `v1.5.9` after confirming its image digest matches exactly what `:stable` was already resolving to (no behavior change, just removes the float) — confirmed live via the container's own startup log (`whiteboard@1.5.9`) — matches the Nextcloud `whiteboard` app's version exactly, since the app and this backend are versioned/released together.

## What `whiteboard.${DOMAIN}` actually is — don't visit it directly

Same relationship as [ONLYOFFICE](onlyoffice.md) is to Nextcloud Office: this container is a real-time collaboration *backend* (a WebSocket relay for syncing strokes between people editing the same board live), not a standalone app. It has no login page, no board list, no "new whiteboard" button of its own. The actual canvas UI is part of Nextcloud's own `whiteboard` app — open it via **Files → + New → Whiteboard**, or open an existing `.whiteboard` file, and Nextcloud loads the canvas and connects to this backend invisibly. Day to day, ignore this subdomain entirely and just use Nextcloud normally.

## Setup

```bash
cp services/whiteboard/.env.example services/whiteboard/.env
# JWT_SECRET_KEY is already generated in .env if you're reading this after
# the initial setup pass — otherwise generate one: openssl rand -hex 32
uv run homeserver.py dev up whiteboard
```

Then in Nextcloud, **Settings → Administration → Whiteboard**:

```text
Whiteboard server URL: https://whiteboard.${DOMAIN}
Shared secret: <same value as JWT_SECRET_KEY in services/whiteboard/.env>
```

Equivalent via `occ` if preferred:

```bash
docker exec -u www-data nextcloud php occ config:app:set whiteboard collabBackendUrl --value="https://whiteboard.${DOMAIN}"
docker exec -u www-data nextcloud php occ config:app:set whiteboard jwt_secret_key --value="<same value as JWT_SECRET_KEY>"
```

No "internal address" optimization here unlike ONLYOFFICE — the Nextcloud **browser client** connects to this backend directly over WebSocket for live collaboration, so the configured URL has to be the real public one reachable from outside the Docker network, not the container-internal name. The backend's own server-to-server calls back to Nextcloud (to read/write whiteboard file content) use `NEXTCLOUD_URL`, which **is** set to the internal container address (`http://nextcloud`, in `compose.yml`) for the same hairpin-avoidance reason as ONLYOFFICE.

## Troubleshooting: admin page shows "Failed to verify the connection: timeout"

Confirmed harmless with hard evidence, not just inference — every layer of the real path was independently tested:

1. **Plain HTTPS reachability**: `nextcloud` container → public `collabBackendUrl` → `200` in well under a second.
2. **An actual WebSocket handshake over the full public chain** (internet → Cloudflare → `cloudflared` → `nginx-plain` → `whiteboard` container) — a real socket.io polling handshake to get a session id, then upgrading it, returns a clean `HTTP/1.1 101 Switching Protocols` with a valid `Sec-Websocket-Accept`. (First attempt via `curl` returned a `400` — that was curl negotiating HTTP/2 by default, which doesn't perform the classic `Connection: Upgrade` handshake; forcing `--http1.1` — the same mechanism a real browser's WebSocket client uses — succeeded immediately.)
3. **Real usage**: browser sessions actually joining rooms and broadcasting live updates in `docker logs whiteboard`, and a drawing confirmed saved and visible in Files.

So the entire infrastructure — proxy, tunnel, WebSocket upgrade, container — is verified working end to end. Only Nextcloud's own PHP-side pre-flight "verify" button doesn't confirm it, which matches a documented, known false-negative in the upstream project's own issue tracker (nextcloud/whiteboard#173): that check attempts something stricter than plain reachability (likely a WebSocket handshake attempted from PHP itself, which behaves differently than a browser's) and is known to be unreliable specifically behind a reverse proxy/tunnel. Upstream's own resolution for that issue was a documentation clarification, not a code fix, since the architecture is "client-first" — the real browser's own WebSocket connection is what matters, not this pre-flight check. Unlike ONLYOFFICE, there's no separate internal-address field to route around this with; just ignore the banner.

## Fixed: whiteboard content wasn't actually saving — unrelated to the banner above

**Symptom:** real-time collaboration (drawing, live cursor/stroke sync between browsers) appeared to work fine, but `docker logs whiteboard` showed clean `[SOCKET]`/room-join activity while `nextcloud.log` showed a **separate, repeating failure** — every auto-save attempt (`PUT /index.php/apps/whiteboard/<id>`, every 10-20s) returned `500`:

```
Error syncing whiteboard data: The antivirus executable could not be found at /usr/bin/clamscan
Exception handled: RuntimeException ... files_antivirus/lib/Scanner/LocalClam.php ... status_code: 500
```

**Root cause:** unrelated to this service — the `files_antivirus` app (see `docs/services/nextcloud.md`) was enabled and configured to shell out to a local `clamscan` binary that doesn't exist in the stock Nextcloud image, with no separate ClamAV container ever set up to back it. Any file write that triggers a scan — including the whiteboard's own auto-save — failed with a 500. The live collaboration you see in the browser is pure WebSocket cursor/stroke sync through this container and never touches that broken code path, which is exactly why it looked like everything worked while saves were silently failing underneath — closing every browser tab with nobody's session persisted would have lost the drawing.

**Fix applied:** `files_antivirus` disabled (`occ app:disable files_antivirus`) until a real ClamAV backend is set up — it wasn't actually scanning anything before either (silently broken), so disabling it loses no real protection, it just stops it from actively blocking saves. Setting up a proper ClamAV container (same standalone-service pattern as this app and ONLYOFFICE) is planned as a follow-up; re-enable `files_antivirus` only once that's wired up and confirmed working, or every file operation that triggers a scan will fail the same way again.

## Storage strategy — no database, nothing to lose

Runs with `STORAGE_STRATEGY=lru` (the image's own default) — in-memory session state only, no Redis, no persistent volume, nothing this container holds is durable. This is intentional and fine at family scale: the actual whiteboard *content* is saved into Nextcloud's own file storage (a `.whiteboard` file, same as any other file — versioned, shared, backed up the normal Nextcloud way); this container only holds the live, ephemeral collaboration session (who's connected, in-flight cursor/stroke sync). Losing that on a restart just means everyone's live session reconnects — no data loss. `STORAGE_STRATEGY=redis` is upstream's documented option for multi-node clusters, not relevant here with a single instance.

## Health endpoint

No documented health endpoint upstream — found by testing the running container directly: `/status` returns `200`. `compose.yml`'s healthcheck (`wget --spider`, since the image has no `curl`) and `services/landing/nginx.conf`'s `/health/whiteboard` route both use this path.

## Reverse proxy notes

`services/nginx-plain/templates/default.conf.template`'s `whiteboard.${DOMAIN}` block proxies WebSocket traffic (`proxy_http_version 1.1` + conditional `Connection: upgrade`, same pattern as Guacamole/ONLYOFFICE) since real-time collaboration runs over `socket.io`, plus a long `proxy_read_timeout 3600s` so idle-but-open collaboration sessions aren't cut off.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
