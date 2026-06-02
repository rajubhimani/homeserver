# 07 — Landing Page

[← Immich](06-immich.md) | [Home](../setup.md) | [Next: Maintenance →](08-maintenance.md)

---

A service dashboard served by Nginx Alpine. Shows all services with **live status indicators** —
green when up, red when down, rechecked every 60 seconds.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | Dashboard UI template with placeholders |
| `entrypoint.sh` | Replaces placeholders with `.env` values at startup |
| `nginx.conf` | Serves HTML + `/health/*` proxy endpoints |
| `docker-compose.yml` | Base config (no ports) |
| `compose.dev.yml` | Exposes port `8080` on all interfaces |
| `compose.prod.yml` | Exposes port `8080` on `127.0.0.1` only |
| `.env` | `DOMAIN`, `SITE_NAME`, `TAGLINE`, `AUTHOR`, `LOCATION` |

## Dynamic configuration

The landing page is fully dynamic — no domain or personal info is hardcoded.
Set these in `landing/.env`:

```env
DOMAIN=yourdomain.com
SITE_NAME=MyServer
TAGLINE=Your data, your hardware, your control.
AUTHOR=Your Name
LOCATION=Your City
```

`entrypoint.sh` runs `sed` at container start to replace placeholders in `index.html`
before nginx serves it.

## How live status works

The browser fetches `/health/<service>` (same-origin, no CORS issues).
Nginx proxies each request to the real container via the internal Docker network.

```text
Browser → /health/nextcloud → nginx (landing) → nextcloud:80
```

Health endpoints are in `nginx.conf`. Docker's internal DNS (`127.0.0.11`) with
`set $upstream` defers resolution — the landing container starts even if other services are down.

Redirects (e.g. GitLab's 302) are treated as online using `redirect: 'manual'` in the
JS fetch call — opaque responses count as up.

## Start

```bash
sh homeserver.sh dev up landing
```

## Access

- **Cloudflare path:** `https://yourdomain.com` (nginx-plain proxies `landing:80`)
- **Tailscale / dev path:** `http://<server-ip>:8080`

## Add a new service to the dashboard

1. Add a card in `landing/index.html` under the appropriate section
2. Add the service subdomain to `SERVICE_SUBDOMAINS` in the `<script>` block
3. Add a `/health/<service>` location block in `landing/nginx.conf`
4. Restart landing to reload nginx:

```bash
sh homeserver.sh dev up landing
```

---

[← Immich](06-immich.md) | [Home](../setup.md) | [Next: Maintenance →](08-maintenance.md)
