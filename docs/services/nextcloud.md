# Nextcloud

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** File storage + sharing, replaces Google Drive.
**Port:** `8081` (host) → `80` (container) | **Data:** `service_data/nextcloud/`

## Setup

```bash
cp nextcloud/.env.example nextcloud/.env
sh homeserver.sh dev up nextcloud
```

**Admin password in `.env` must not contain `$`** — Docker Compose interprets `$VAR` patterns as variable references and silently mangles passwords containing `$`. Use `openssl rand -hex 20` to generate a safe password.

## Architecture notes

- Uses **partial volume mounts** (config, data, custom_apps, version.php) — do **not** mount the full `/var/www/html`
- Has a `before-starting` hook that runs `rsync` on every startup to populate PHP files
- Trusted proxies are set in compose — required for correct IP forwarding behind nginx

## Trusted proxies / HTTPS gotcha — `occ` is the real fix

`NEXTCLOUD_TRUSTED_PROXIES` in `compose.yml` is only applied by the official image during **first-time initialization**. If Nextcloud was already set up before that env var existed (or before `DOMAIN`/network changes), it silently has no effect on an existing install. Fix/verify with `occ` directly instead — this persists to `config.php` on the data volume and survives restarts:

```bash
docker exec nextcloud php occ config:system:set trusted_proxies 0 --value="172.18.0.0/16"   # match `docker network inspect homeserver`
docker exec nextcloud php occ config:system:set overwriteprotocol --value="https"
docker exec nextcloud php occ config:system:set overwrite.cli.url --value="https://nextcloud.${DOMAIN}"
```

Missing `overwriteprotocol`/`trusted_proxies` causes Nextcloud to think every request is plain HTTP behind the proxy — manifests as unhealthy status, 503s, redirect loops, or broken links.

## Incident: health-check 400s mistaken for a performance problem (2026-07-02)

Nextcloud validates the `Host` header against `trusted_domains` on **every** request, including from `landing/nginx.conf`'s `/health/nextcloud` proxy. That block originally did `proxy_pass http://nextcloud:80/;` (bare root, no `Host` override), which arrives with an untrusted `Host` and gets rejected with a 400.

Root cause traced 2026-07-02: the landing page's client-side status poller hit this endpoint every ~30s continuously, all day, producing a stream of 400s in Nextcloud's access log with the *proxy's* IP (not a real client) — easy to mistake for a performance/DB problem when it's actually just a broken health check.

**Fix:** point the health check at `/status.php` (the same lightweight endpoint Nextcloud's own Docker healthcheck already uses successfully) with `proxy_set_header Host localhost;` explicitly set.

**General lesson for any service's `/health/<service>` block:** if the app validates the `Host` header (trusted domains/allowed hosts/CSRF origin checks — Nextcloud, and potentially others), a bare `proxy_pass $upstream/;` health check will silently 400 forever; explicitly set `proxy_set_header Host localhost;` (or whatever the app trusts) on that specific location block.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
