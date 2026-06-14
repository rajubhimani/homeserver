# 11 — Services Reference

[← New Services](10-new-services.md) | [Home](../setup.md)

---

Quick reference for all services — ports, proxy config, and notes.

---

## Service Tiers

Services are grouped into three additive tiers. Each tier builds on the previous.

| Tier | Command | Services |
| --- | --- | --- |
| `min` | `sh homeserver.sh dev up min` | dozzle, cloudflared, nginx-plain, landing |
| `core` | `sh homeserver.sh dev up core` | min + nextcloud |
| `all` | `sh homeserver.sh dev up all` | core + every extra service |

`down all` always stops everything in reverse order — no list to maintain.

**Extra services** (started with `up all` or individually):
vaultwarden, gitea, forgejo, gitlab, immich, jellyfin, paperless, stirling-pdf-lite,
mealie, uptime-kuma, stalwart, snappymail, roundcube, syncthing, authentik, ntfy,
miniflux, audiobookshelf, conduit, openproject, plane, crater, and more.

---

## Port Reference

| Service | Container | Dev port | Container port | Tier |
| --- | --- | --- | --- | --- |
| nginx-plain | `nginx-plain` | 80 / 443 | 80 / 443 | min |
| Landing Page | `landing` | 8080 | 80 | min |
| Dozzle | `dozzle` | 9999 | 8080 | min |
| Nextcloud | `nextcloud` | 8081 | 80 | core |
| Immich | `immich-server` | 2283 | 2283 | extra |
| Jellyfin | `jellyfin` | 8096 | 8096 | extra |
| Vaultwarden | `vaultwarden` | 8200 | 80 | extra |
| Paperless-ngx | `paperless` | 8010 | 8000 | extra |
| Stirling PDF Lite | `stirling-pdf-lite` | 8090 | 8080 | extra |
| Stirling PDF Full | `stirling-pdf` | 8089 | 8080 | extra (manual) |
| Mealie | `mealie` | 9925 | 9000 | extra |
| Gitea | `gitea` | 3000 / 2222 (SSH) | 3000 / 22 | extra |
| Forgejo | `forgejo` | 3002 / 2223 (SSH) | 3000 / 22 | extra |
| GitLab CE | `gitlab` | 8085 / 2224 (SSH) | 80 / 22 | extra |
| Uptime Kuma | `uptime-kuma` | 3001 | 3001 | extra |
| Headscale | `headscale` | 8086 | 8080 | extra (manual) |
| Syncthing | `syncthing` | 8087 | 8384 | extra |
| Authentik | `authentik-server` | 8088 | 9000 | extra |
| Stalwart Mail | `stalwart` | 8091 | 8080 | extra |
| Ntfy | `ntfy` | 8092 | 80 | extra |
| Miniflux | `miniflux` | 8093 | 8080 | extra |
| Audiobookshelf | `audiobookshelf` | 8094 | 80 | extra |
| Conduit (Matrix) | `conduit` | 8095 / 8448 (fed.) | 6167 | extra |
| Snappymail | `snappymail` | 8097 | 8888 | extra |
| Roundcube | `roundcube` | 8098 | 80 | extra |
| OpenProject | `openproject` | 8099 | 80 | extra |
| Plane | `plane-proxy` | 8100 | 80 | extra |
| Crater | `crater` | 8101 | 80 | extra |
| Nginx Proxy Manager | `nginx-proxy-manager` | 80 / 443 / 81 (admin) | same | extra (optional) |

---

## Reverse Proxy Config

### nginx-plain (default)

Config lives in `nginx-plain/templates/default.conf.template`.
Domain is injected from `DOMAIN` in root `.env` at container start.

Each service gets a `server_name <service>.<DOMAIN>` block pointing to its container name.
No UI — edit the template file and recreate the container to reload.

### Nginx Proxy Manager (optional)

UI at `http://<server>:81`. Add proxy hosts manually through the web interface.

> Run only one proxy at a time — both bind to ports 80/443.
> To switch: replace `nginx-plain` with `nginx` in `SERVICES_CORE` in `homeserver.sh`.

**Forward Hostname** = Docker container name (NPM resolves via `homeserver` network).
**Scheme** = `http` for all (Cloudflare handles TLS).

| Domain | Forward Hostname | Forward Port |
| --- | --- | --- |
| `nextcloud.yourdomain.com` | `nextcloud` | `80` |
| `immich.yourdomain.com` | `immich-server` | `2283` |
| `photos.yourdomain.com` | `immich-server` | `2283` |
| `jellyfin.yourdomain.com` | `jellyfin` | `8096` |
| `vaultwarden.yourdomain.com` | `vaultwarden` | `80` |
| `paperless.yourdomain.com` | `paperless` | `8000` |
| `stirling-pdf.yourdomain.com` | `stirling-pdf-lite` | `8080` |
| `mealie.yourdomain.com` | `mealie` | `9000` |
| `gitea.yourdomain.com` | `gitea` | `3000` |
| `forgejo.yourdomain.com` | `forgejo` | `3000` |
| `gitlab.yourdomain.com` | `gitlab` | `80` |
| `uptime-kuma.yourdomain.com` | `uptime-kuma` | `3001` |
| `status.yourdomain.com` | `uptime-kuma` | `3001` |
| `dozzle.yourdomain.com` | `dozzle` | `8080` |
| `mail.yourdomain.com` | `stalwart` | `8080` |
| `webmail.yourdomain.com` | `snappymail` | `8888` |
| `roundcube.yourdomain.com` | `roundcube` | `80` |
| `syncthing.yourdomain.com` | `syncthing` | `8384` |
| `authentik.yourdomain.com` | `authentik-server` | `9000` |
| `ntfy.yourdomain.com` | `ntfy` | `80` |
| `miniflux.yourdomain.com` | `miniflux` | `8080` |
| `audiobookshelf.yourdomain.com` | `audiobookshelf` | `80` |
| `matrix.yourdomain.com` | `conduit` | `6167` |
| `openproject.yourdomain.com` | `openproject` | `80` |
| `plane.yourdomain.com` | `plane-proxy` | `80` |
| `crater.yourdomain.com` | `crater` | `80` |

---

## Service Notes

### Nextcloud

- Volumes: partial mounts (config, data, custom_apps, version.php) — do **not** mount full `/var/www/html`
- A before-starting hook runs rsync on every startup to populate PHP files
- Trusted proxies set in compose — required for correct IP forwarding behind nginx

### Immich

- Mobile app: connect to `https://immich.yourdomain.com` or `https://photos.yourdomain.com`
- Admin account created on first browser visit (no env var)
- ML (face recognition): `sh homeserver.sh dev up immich --profile ml`
- Uses custom Postgres image with pgvector (`ghcr.io/immich-app/postgres`)

### Vaultwarden

- Signups disabled by default (`SIGNUPS_ALLOWED=false`) — invite users via `/admin` panel
- Admin token: `ADMIN_TOKEN` in `.env` (`openssl rand -base64 48`)

### Paperless-ngx

- Admin account auto-created from `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` on first start
- Consumption folder: drop PDFs into `service_data/paperless/consume/` to auto-import

### Stirling PDF Lite vs Full

- **Lite** (`latest-ultra-lite`): in `SERVICES_EXTRA`, ~200MB RAM, core PDF ops
- **Full** (`latest`): manual start only, ~1.5GB RAM, OCR + LibreOffice

### Mealie

- Default login: `changeme@example.com` / `MyPassword` — change immediately
- Signups disabled by default (`ALLOW_SIGNUP=false`)

### Gitea

- SSH clone port: `2222` (host) → `22` (container)
- Setup wizard skipped (`GITEA__security__INSTALL_LOCK=true`)
- Actions runner: set `GITEA_RUNNER_TOKEN` in `.env`, then `--profile runner`

### Forgejo

- SSH clone port: `2223` (host) → `22` (container)
- Image: `codeberg.org/forgejo/forgejo:15`
- Config env vars use `FORGEJO__` prefix
- Setup wizard skipped (`FORGEJO__security__INSTALL_LOCK=true`)
- Actions runner: `sh homeserver.sh dev up forgejo --profile runner`

### GitLab CE

- Requires ~4 GB RAM minimum; takes 2–3 min to start on first launch
- All config via `GITLAB_OMNIBUS_CONFIG` in compose (Ruby format)
- SSH clone port: `2224`; HTTP-only internally (`nginx['listen_https'] = false`)
- GitLab Runner: `sh homeserver.sh dev up gitlab --profile runner`

### Stalwart Mail

- Combined SMTP + IMAP + admin UI in one container
- Ports: `25` (SMTP), `587` (submission), `993` (IMAPS), `143` (IMAP), `8080` (admin)
- Run setup wizard at `http://<ip>:8091/setup` on first start
- Healthcheck uses `curl -s` without `-f` — returns 404 in bootstrap mode (normal)
- Webmail clients connect to `stalwart:143` (IMAP) and `stalwart:587` (SMTP)

### Snappymail

- Fast, minimal webmail — good default for daily use
- Configure IMAP/SMTP via admin panel at `http://<ip>:8097/?admin`
- Default admin password: set `SNAPPYMAIL_ADMIN_PASSWORD` in `.env`

### Roundcube

- Full-featured webmail with plugins, address book, calendar
- Admin at `/roundcubemail/?_task=settings`
- Configure IMAP/SMTP in `roundcube/.env`

### Syncthing

- Peer-to-peer sync — no central server
- Web UI at `http://<ip>:8087` — set a password immediately on first visit
- Health endpoint: `/rest/noauth/health`

### Authentik

- Identity provider — SSO, OAuth2, OIDC, SAML
- Requires `AUTHENTIK_SECRET_KEY` in `.env` (`openssl rand -hex 32`) before first start
- Admin UI at `http://<ip>:8088/if/admin/`
- Default admin: `akadmin` — set password on first login

### Ntfy

- Push notifications to phone/desktop via simple HTTP POST
- No login by default — add `NTFY_AUTH_FILE` to enable auth
- SSE streaming — nginx config includes `proxy_buffering off`

### Miniflux

- Minimal RSS reader — no JavaScript frontend
- Admin account set via `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`
- Health endpoint: `/healthcheck`

### Audiobookshelf

- Streams audiobooks and podcasts; mobile app available
- Admin account created on first browser visit
- Health endpoint: `/ping`

### Conduit (Matrix)

- Lightweight Matrix homeserver
- Distroless image — no shell available, no healthcheck
- Configure via `conduit/conduit.toml`
- Set `CONDUIT_ALLOW_REGISTRATION=true` temporarily to create first accounts

### OpenProject

- All-in-one project management with bundled Postgres
- Requires `SECRET_KEY_BASE` in `.env` (`openssl rand -hex 64`)
- `OPENPROJECT_HTTPS=false` — Cloudflare handles TLS
- Default login: `admin` / `admin` — change on first login

### Plane

- Multi-container: postgres, valkey, rabbitmq, minio, api, worker, beat, web, proxy
- Requires `SECRET_KEY` (`openssl rand -hex 32`) and all DB/queue passwords in `.env`
- Needs ~4 GB RAM
- Access via `plane-proxy` on port `8100`

### Crater

- Laravel invoicing app with MariaDB
- Requires `APP_KEY` in `.env` (`echo "base64:$(openssl rand -base64 32)"`)
- Run setup wizard on first visit at `http://<ip>:8101`

### Uptime Kuma

- Admin account created on first browser visit
- Add monitors for each service subdomain

### Dozzle

- No login by default — restrict via nginx access control if exposed publicly
- SSE streaming — nginx config includes `proxy_buffering off`

### Portainer CE

- Port `9000` (HTTP) or `9443` (HTTPS)
- Create admin account on first visit — prompt times out after a few minutes

### Dockge

- Port `5001`
- `DOCKGE_STACKS_DIR` must be an absolute path — relative paths silently break stack management
- Only manages stacks it created; use Portainer to manage existing running containers

---

[← New Services](10-new-services.md) | [Home](../setup.md)
