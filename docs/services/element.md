# Element

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Web client for [Conduit](conduit.md). Conduit is a distroless, backend-only Matrix homeserver with no frontend at all — Element Web is what turns it into something you can actually chat with in a browser.
**Port:** `8108` → `80` (container) | **Data:** none — Element Web is stateless; all session/room state lives in the browser (IndexedDB), not on the server

## Setup

```bash
cp element/.env.example element/.env
uv run homeserver.py dev up element
```

Then visit `https://element.yourdomain.com` (or `http://<server-ip>:8108` in dev). It comes pre-configured to log in against `conduit.yourdomain.com` — no manual homeserver entry needed, unlike pointing app.element.io at a custom server.

To register your first account, follow [conduit.md](conduit.md)'s registration-toggle steps first (`ALLOW_REGISTRATION=true` in `conduit/.env`), then use Element's own registration form.

## Architecture

- Image: `vectorim/element-web` — the official upstream image, built on `nginxinc/nginx-unprivileged` (runs as a non-root `nginx` user, unlike plain `nginx:alpine`)
- No database, no named volume, no `service_data/` subdirectory — a pure static SPA plus a couple of small init scripts baked into the image
- `element/config.json` is bind-mounted read-only to `/app/config.json`. It contains `DOMAIN_PLACEHOLDER` in `default_server_config.m.homeserver.base_url`/`server_name` rather than a real domain, since this repo's convention is to never hardcode the domain in a committed file — `${DOMAIN}` gets substituted in at container start instead (see below)
- `element/docker-entrypoint.d/19-set-homeserver.sh` is bind-mounted to `/docker-entrypoint.d/19-set-homeserver.sh` inside the container. The upstream image already ships its own `/docker-entrypoint.d/18-load-element-modules.sh`, which the base `nginxinc/nginx-unprivileged` entrypoint runs automatically (numbered scripts execute in sort order); that script copies `/app/config*.json` into `/tmp/element-web-config/config.json` — the actual path nginx serves `/config.json` from (see the image's `default.conf.template`). Our script is numbered `19` so it runs *after* that copy, and does an in-place `sed` substituting `DOMAIN_PLACEHOLDER` → the real `$DOMAIN` env var on the `/tmp` copy
- **Why `/tmp` and not `/app` directly:** `/app` is owned by root from the image's build stage and isn't writable by the unprivileged `nginx` user the container actually runs as, so any substitution has to target the writable `/tmp/element-web-config/` copy instead — mirroring exactly what the base image's own module-loading script already does for the same reason
- `DOMAIN` reaches the container via `environment: DOMAIN: ${DOMAIN}` in `compose.yml`, populated the normal way — `homeserver.py` injects `DOMAIN` into every service's `docker compose` invocation automatically

## Gotchas

- **The entrypoint script must stay executable.** `/docker-entrypoint.d/*.sh` is only picked up by the base image's entrypoint if the file has the executable bit set — this repo's `element/docker-entrypoint.d/19-set-homeserver.sh` was committed with `chmod +x` already applied so a fresh `git clone` on Linux preserves it. If you ever recreate this file, `chmod +x` it again before committing.
- **If Element shows the upstream `matrix.org` homeserver instead of your own on first load:** the substitution script didn't run, or ran before (not after) the base image's `18-load-element-modules.sh`. Confirm via `docker exec element cat /tmp/element-web-config/config.json` — it should show your real domain, not `DOMAIN_PLACEHOLDER` or `matrix.org`. If it still shows `DOMAIN_PLACEHOLDER`, check the script is still executable inside the container (`docker exec element ls -la /docker-entrypoint.d/`).
- **Federation/registration:** Element itself has no registration toggle — that lives entirely on the Conduit side (`ALLOW_REGISTRATION` in `conduit/.env`). Element just reflects whatever the homeserver allows.
- Unlike most services in this stack, Element needs no `X-Forwarded-Proto` or reverse-proxy scheme handling of its own — it's a static SPA with no server-side URL generation depending on request scheme.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
