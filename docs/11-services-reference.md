# 11 — Services Reference

[← New Services](10-new-services.md) | [Home](../setup.md)

---

Quick reference for all services — ports, NPM proxy config, service groups, and notes.

---

## Service Groups

| Group | Services | Command |
| --- | --- | --- |
| `all` | All services in startup order | `sh homeserver.sh dev up all` |
| `core` | dozzle → nginx → landing → nextcloud | `sh homeserver.sh dev up core` |
| *(manual)* | stirling-pdf (full) | `sh homeserver.sh dev up stirling-pdf` |

**Startup order (`all`):**

```text
dozzle → nginx → landing → nextcloud → vaultwarden → gitea → forgejo → gitlab → immich
→ jellyfin → paperless → stirling-pdf-lite → mealie → uptime-kuma
```

Shutdown is always the reverse. Dozzle starts first and stops last for visibility.

---

## Service Overview

| Service | Container | Port | Data path | Always on |
| --- | --- | --- | --- | --- |
| Nginx Proxy Manager | `nginx-proxy-manager` | 80 / 443 | `data/nginx/` | ✓ |
| Landing Page | `landing` | 8080 | stateless (repo) | ✓ |
| Dozzle | `dozzle` | 9999 | none | ✓ |
| Nextcloud | `nextcloud` | 8081 | `service_data/nextcloud/` | ✓ |
| Immich | `immich-server` | 2283 | `service_data/immich/` | ✓ |
| Jellyfin | `jellyfin` | 8096 | `service_data/jellyfin/` | ✓ |
| Vaultwarden | `vaultwarden` | 8200 | `service_data/vaultwarden/` | ✓ |
| Paperless-ngx | `paperless` | 8010 | `service_data/paperless/` | ✓ |
| Stirling PDF Lite | `stirling-pdf-lite` | 8090 | `service_data/stirling-pdf-lite/` | ✓ |
| Mealie | `mealie` | 9925 | `service_data/mealie/` | ✓ |
| Gitea | `gitea` | 3000 / 2222 | `service_data/gitea/` | ✓ |
| Forgejo | `forgejo` | 3002 / 2223 | `service_data/forgejo/` | ✓ |
| GitLab CE | `gitlab` | 8085 / 2224 | `service_data/gitlab/` | ✓ |
| Uptime Kuma | `uptime-kuma` | 3001 | `service_data/uptime-kuma/` | ✓ |
| Stirling PDF (Full) | `stirling-pdf` | 8089 | `service_data/stirling-pdf/` | Manual |
| Headscale | `headscale` | 8086 | `service_data/headscale/` | Manual |

---

## NPM Proxy Hosts

Add these in Nginx Proxy Manager → Proxy Hosts.

> **Forward Hostname** = Docker container name. NPM resolves it via the shared `homeserver` network.  
> **Scheme** = `http` for all (Cloudflare handles TLS externally).

| Domain | Forward Hostname | Forward Port | Access List | Notes |
| --- | --- | --- | --- | --- |
| `nextcloud.yourdomain.com` | `nextcloud` | `80` | — | |
| `immich.yourdomain.com` | `immich-server` | `2283` | — | |
| `jellyfin.yourdomain.com` | `jellyfin` | `8096` | — | |
| `vaultwarden.yourdomain.com` | `vaultwarden` | `80` | — | |
| `paperless.yourdomain.com` | `paperless` | `8000` | — | |
| `stirling-pdf-lite.yourdomain.com` | `stirling-pdf-lite` | `8080` | ✓ Required | See auth note below |
| `stirling-pdf.yourdomain.com` | `stirling-pdf` | `8080` | — | Manual start only |
| `mealie.yourdomain.com` | `mealie` | `9000` | — | |
| `gitea.yourdomain.com` | `gitea` | `3000` | — | |
| `forgejo.yourdomain.com` | `forgejo` | `3000` | — | |
| `gitlab.yourdomain.com` | `gitlab` | `80` | — | |
| `uptime-kuma.yourdomain.com` | `uptime-kuma` | `3001` | — | |
| `dozzle.yourdomain.com` | `dozzle` | `8080` | — | |
| `photos.yourdomain.com` | `immich-server` | `2283` | — | Alias for Immich |

---

## NPM Access List Setup (Stirling PDF Lite)

The ultra-lite image has no built-in login. Authentication is handled at the NPM layer.

1. NPM → **Access Lists** → **Add Access List**
   - Name: `Stirling PDF Lite`
   - **Authorization tab** → add username + password
   - **Access tab** → add `Allow` → `0.0.0.0/0`
2. NPM → **Proxy Hosts** → `stirling-pdf-lite.yourdomain.com` → Edit
   - **Access List** → select `Stirling PDF Lite`

Users will see a browser login prompt before reaching the app.

---

## Service Notes

### Nextcloud

- Volumes: partial mounts (config, data, custom_apps, version.php) — do **not** mount full `/var/www/html`
- A before-starting hook runs rsync on every startup to populate PHP files
- Trusted proxies: `nginx-proxy-manager` set in compose — required for correct IP forwarding

### Immich

- Mobile app: connect to `https://photos.yourdomain.com` or `https://immich.yourdomain.com`
- Admin account created on first browser visit (no env var)
- ML (face recognition): start with `sh homeserver.sh dev up immich --profile ml`

### Vaultwarden

- Signups disabled by default (`SIGNUPS_ALLOWED=false` in `.env`) — invite users via `/admin` panel
- Admin token: set `ADMIN_TOKEN` in `.env` (`openssl rand -base64 48`)
- To allow signups: set `SIGNUPS_ALLOWED=true` in `.env` and restart

### Paperless-ngx

- Resource limited: `PAPERLESS_TASK_WORKERS=1`, `PAPERLESS_THREADS_PER_WORKER=1`
- Admin account auto-created from `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` on first start
- Consumption folder: drop PDFs into `data/paperless/consume/` to auto-import

### Stirling PDF Lite vs Full

- **Lite** (`latest-ultra-lite`): always on, ~200MB RAM, core PDF ops only, auth via NPM
- **Full** (`latest`): manual start only, ~1.5GB RAM, OCR + LibreOffice, start when needed

### Mealie

- Default login: `changeme@example.com` / `MyPassword` — change immediately after first login
- Signups disabled by default (`ALLOW_SIGNUP=false` in `.env`)
- To allow signups: set `ALLOW_SIGNUP=true` in `.env` and restart

### Gitea

- SSH clone port: `2222` (mapped from container's 22)
- Setup wizard skipped automatically (`GITEA__security__INSTALL_LOCK=true` in compose)
- Registration disabled by default (`DISABLE_REGISTRATION=true` in `.env`)
- To allow signups: set `DISABLE_REGISTRATION=false` in `.env` and restart
- Actions (CI/CD) enabled by default (`GITEA__actions__ENABLED=true` in compose)
- Actions runner is optional — set `GITEA_RUNNER_TOKEN` in `.env` (from Site Admin → Runners → Create Runner), then:
  ```bash
  sh homeserver.sh dev up gitea --profile runner
  ```

### Forgejo

- Community-driven Gitea fork — same UX, independent release cycle
- SSH clone port: `2223` (mapped from container's 22)
- Config env vars use `FORGEJO__` prefix (e.g. `FORGEJO__database__HOST`)
- Image: `codeberg.org/forgejo/forgejo:15` (pinned major version)
- Setup wizard skipped automatically (`FORGEJO__security__INSTALL_LOCK=true` in compose)
- Registration disabled by default (`DISABLE_REGISTRATION=true` in `.env`)
- To allow signups: set `DISABLE_REGISTRATION=false` in `.env` and restart
- Actions (CI/CD) enabled by default (`FORGEJO__actions__ENABLED=true` in compose)
- Actions runner is optional — start then register:
  ```bash
  sh homeserver.sh dev up forgejo --profile runner
  docker exec -it forgejo-runner forgejo-runner register
  ```

### GitLab CE

- Full DevOps platform — heavier than Gitea/Forgejo (~4GB RAM minimum)
- Built-in Postgres, Redis, and nginx — no separate database container needed
- All config via `GITLAB_OMNIBUS_CONFIG` in compose (Ruby format)
- SSH clone port: `2224` (mapped from container's 22)
- Web port: `8085` (NPM proxies to `gitlab:80` internally)
- Admin password set on first browser visit at `/users/sign_in`
- Registration disabled by default (`SIGNUP_ENABLED=false` in `.env`)
- To allow signups: set `SIGNUP_ENABLED=true` in `.env` and restart
- GitLab Runner is optional — start with `--profile runner`, then register it:
  ```bash
  sh homeserver.sh dev up gitlab --profile runner
  docker exec -it gitlab-runner gitlab-runner register
  ```

### Dozzle

- No login by default — consider NPM access list if exposed publicly

### Portainer CE

- Port `9000` (HTTP) or `9443` (HTTPS)
- Create admin account on first browser visit — do it immediately, the prompt times out after a few minutes
- Sees all running containers including existing homeserver services

### Dockge

- Port `5001`
- Create admin account on first browser visit
- **Stacks directory gotcha:** `DOCKGE_STACKS_DIR` in `.env` must be an absolute path and must be identical inside and outside the container. Dockge runs `docker compose` commands using the host path directly — a relative path or mismatched mount silently breaks stack management.
- Create the directory before starting: `mkdir -p <DOCKGE_STACKS_DIR>`
- Dockge only manages stacks it creates in that directory — existing homeserver services will not appear. Use Portainer if you need to see and manage already-running containers.

---

[← New Services](10-new-services.md) | [Home](../setup.md)
