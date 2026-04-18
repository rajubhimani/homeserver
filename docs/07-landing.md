# 07 — Landing Page

[← Immich](06-immich.md) | [Home](../setup.md) | [Next: Maintenance →](08-maintenance.md)

---

A service dashboard served by Nginx Alpine. Shows all services with **live status indicators** — green when up, red when down, rechecked every 60 seconds.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | Dashboard UI with status badges |
| `nginx.conf` | Serves HTML + `/health/*` proxy endpoints |
| `docker-compose.yml` | Base config (no ports) |
| `compose.dev.yml` | Exposes port `8080` on all interfaces |
| `compose.prod.yml` | Exposes port `8080` on `127.0.0.1` only |

## How live status works

The browser fetches `/health/<service>` (same-origin, no CORS issues). Nginx proxies each request to the real container on the internal Docker network and returns the actual HTTP status. If a container is down, nginx gets a connection refused and returns `502` — the badge turns red.

```text
Browser → /health/immich → nginx (landing) → immich-server:2283
```

Health endpoints are defined in `nginx.conf` using Docker's internal DNS (`127.0.0.11`) with `set $upstream` to defer resolution — so the landing container starts even if other services are down.

## Start

```bash
# dev (port 8080 exposed)
./homeserver.sh landing dev

# prod (port 8080 on localhost only, NPM proxies)
./homeserver.sh landing prod
```

## Access

**Cloudflare path:** `https://yourdomain.com` (NPM proxy host → `landing:80`)  
**Tailscale path:** `http://100.x.x.x:8080`

## Update content

Edit `~/homeserver/landing/index.html` directly — the file is volume-mounted so changes appear on the next browser refresh (no container restart needed).

> Cache-Control headers are set to `no-store` so browsers always fetch the latest version.

## Add a new service to the dashboard

1. Add a card in `index.html` with `data-service="<name>"`
2. Add a `/health/<name>` location in `nginx.conf` pointing to the container
3. Restart the landing container to reload the nginx config:

```bash
cd ~/homeserver/landing
docker compose down && docker compose -f docker-compose.yml -f compose.dev.yml up -d
```

---

[← Immich](06-immich.md) | [Home](../setup.md) | [Next: Maintenance →](08-maintenance.md)
