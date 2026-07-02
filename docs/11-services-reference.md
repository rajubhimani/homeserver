# 11 — Services Reference

[← New Services](10-new-services.md) | [Home](../setup.md)

---

Quick reference for all services — ports, proxy config, and notes.

---

## Service Tiers

Services are grouped into three additive tiers. Each tier builds on the previous.

| Tier | Command | Services |
| --- | --- | --- |
| `min` | `sh homeserver.sh dev up min` | dozzle, cloudflared, nginx-plain, landing, beszel |
| `core` | `sh homeserver.sh dev up core` | min + nextcloud, vaultwarden, forgejo, firefly, immich, appflowy, plane |
| `all` | `sh homeserver.sh dev up all` | core + every extra service |

`down all` always stops everything in reverse order — no list to maintain.

**Extra services** (started with `up all` or individually):
dockge, portainer, openproject, gitlab, jellyfin, paperless, stirling-pdf-lite,
mealie, uptime-kuma, stirling-pdf, stalwart, snappymail, roundcube, syncthing, authentik, ntfy,
miniflux, audiobookshelf, conduit, wg-easy,
headscale, openvpn, invoiceshelf, and more.

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
| Forgejo | `forgejo` | 3002 / 2223 (SSH) | 3000 / 22 | core |
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
| InvoiceShelf | `invoiceshelf` | 8101 | 8080 | extra |
| Firefly III + Importer | `firefly` / `firefly-importer` | 8102 / 8104 | 8080 | core |
| AppFlowy | `appflowy-nginx` | 8103 | 80 | extra |
| Beszel | `beszel` | 8106 | 8090 | min |
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
| `conduit.yourdomain.com` | `conduit` | `6167` |
| `openproject.yourdomain.com` | `openproject` | `80` |
| `plane.yourdomain.com` | `plane-proxy` | `80` |
| `invoiceshelf.yourdomain.com` | `invoiceshelf` | `8080` |
| `firefly.yourdomain.com` | `firefly` | `8080` |
| `firefly-import.yourdomain.com` | `firefly-importer` | `8080` |
| `appflowy.yourdomain.com` | `appflowy-nginx` | `80` |
| `beszel.yourdomain.com` | `beszel` | `8090` |

---

## Service Notes

### Nextcloud

- Volumes: partial mounts (config, data, custom_apps, version.php) — do **not** mount full `/var/www/html`
- A before-starting hook runs rsync on every startup to populate PHP files
- Trusted proxies set in compose — required for correct IP forwarding behind nginx

**Admin password in `.env` must not contain `$`** — Docker Compose interprets `$VAR` patterns as variable references and silently mangles passwords containing `$`. Use `openssl rand -hex 20` to generate a safe password.

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
- Run setup wizard at `http://<ip>:8091/setup` on first start
- Healthcheck uses `curl -s` without `-f` — returns 404 in bootstrap mode (normal)
- Webmail clients connect to `stalwart:143` (IMAP) and `stalwart:587` (SMTP)

**Port mapping (rootless Podman):**

Ports 25 and 143 are privileged (< 1024) — rootless Podman cannot bind them directly. They are remapped on the host:

| Service | Host port | Container port | Privileged? |
| --- | --- | --- | --- |
| SMTP (inbound) | `8025` | `25` | yes — remapped |
| SMTP submission | `8587` | `587` | yes — remapped |
| SMTPS | `8465` | `465` | yes — remapped |
| IMAP | `8143` | `143` | yes — remapped |
| IMAPS | `8993` | `993` | yes — remapped |
| Sieve | `4190` | `4190` | no |
| Admin UI | `8091` | `8080` | no |

External clients and mail servers connect on the standard ports. Add permanent firewall forwarding rules so the OS redirects them to the remapped host ports:

**Fedora / RHEL (firewalld):**
```bash
sudo firewall-cmd --permanent --add-forward-port=port=25:proto=tcp:toport=8025
sudo firewall-cmd --permanent --add-forward-port=port=587:proto=tcp:toport=8587
sudo firewall-cmd --permanent --add-forward-port=port=465:proto=tcp:toport=8465
sudo firewall-cmd --permanent --add-forward-port=port=143:proto=tcp:toport=8143
sudo firewall-cmd --permanent --add-forward-port=port=993:proto=tcp:toport=8993
sudo firewall-cmd --reload
```

**Ubuntu / Debian (iptables):**
```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 25 -j REDIRECT --to-port 8025
sudo iptables -t nat -A PREROUTING -p tcp --dport 587 -j REDIRECT --to-port 8587
sudo iptables -t nat -A PREROUTING -p tcp --dport 465 -j REDIRECT --to-port 8465
sudo iptables -t nat -A PREROUTING -p tcp --dport 143 -j REDIRECT --to-port 8143
sudo iptables -t nat -A PREROUTING -p tcp --dport 993 -j REDIRECT --to-port 8993
# Make persistent across reboots
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

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

**Troubleshooting: process running but not listening on port 6167**

Symptom: `docker top conduit` shows the conduit process running, but `ss -tlnp` shows nothing listening on port 6167, and HTTP connections are refused or reset.

Cause: Conduit emits no startup logs (distroless), so failures are silent. Most common cause is a first-start race or stale RocksDB lock from a previous run.

Fix — restart the container:
```bash
docker restart conduit
```
Verify it's up:
```bash
curl -s http://127.0.0.1:8095/_matrix/client/versions
```
If still failing, check for a stale lock file:
```bash
ls service_data/conduit/data/LOCK
# If present and conduit is not running, delete it:
rm service_data/conduit/data/LOCK
docker restart conduit
```

### OpenProject

- All-in-one project management with bundled Postgres
- Requires `SECRET_KEY_BASE` in `.env` (`openssl rand -hex 64`)
- `OPENPROJECT_HTTPS=true` — tells Rails the connection is secure. Set this to `true` even though the internal hop to OpenProject is plain HTTP — Cloudflare terminates TLS in front of it, and OpenProject needs to know the *original* request was HTTPS, not the internal one. Leaving it `false` causes broken links/redirects.
- Default login: `admin` / `admin` — change on first login

### Plane

- Multi-container: postgres, valkey, rabbitmq, minio, api, worker, beat, web, admin, space, proxy
- **5 frontend/backend images required, not 3**: `plane-web` (main app) is a *different* container from `plane-admin` (serves `/god-mode/*` — onboarding, instance settings) and `plane-space` (serves `/spaces/*` — public views). Routing `/god-mode` through `plane-web` instead of a dedicated `plane-admin` container serves the wrong app bundle — causes React hydration error #423 and the onboarding "Get started" button doing nothing (no network request at all). Verify the official routing by extracting the real Caddyfile from the proxy image: `docker run --rm --entrypoint cat makeplane/plane-proxy:v1.3.1 /etc/caddy/Caddyfile`
- Requires `SECRET_KEY` (`openssl rand -hex 32`) and all DB/queue passwords in `.env`
- Needs ~4 GB RAM
- Access via `plane-proxy` on port `8100`
- `plane-api` needs `APP_BASE_URL`, `ADMIN_BASE_URL`, `SPACE_BASE_URL` set to `https://plane.yourdomain.com` (in addition to `WEB_URL`/`CORS_ALLOWED_ORIGINS`) — without them `GET /api/instances/` returns `null` for these fields
- After editing `plane/Caddyfile`, run `docker restart plane-proxy` — compose does not detect bind-mounted file content changes, only service definition changes

### InvoiceShelf

- InvoiceShelf is the actively maintained successor to Crater — same Laravel + MariaDB stack, same data format
- Image: `invoiceshelf/invoiceshelf` (the original `foralabs/crater` image was made private)
- Requires `APP_KEY` in `.env` (`echo "base64:$(openssl rand -base64 32)"`)
- Run setup wizard on first visit at `http://<ip>:8101`

### Firefly III

- Personal finance manager — income, expenses, budgets, accounts, recurring transactions
- `APP_KEY` must be exactly 32 characters: `openssl rand -hex 16`
- `STATIC_CRON_TOKEN` must be exactly 32 characters: `openssl rand -hex 16`
- First user to register becomes admin; disable further signups at `/settings/configuration`
- Includes `firefly-cron` container that triggers recurring transactions daily at 03:00
- **Data Importer** (`fireflyiii/data-importer`) starts automatically with Firefly — dev port 8104, subdomain `firefly-import.yourdomain.com`
  - One-time admin setup: Firefly III → Profile → OAuth → OAuth Clients → Create new client, redirect URL = `https://firefly-import.yourdomain.com/callback`, uncheck "Keep a secret?"
  - Set the resulting Client ID number in `FIREFLY_III_CLIENT_ID` in `.env` — pre-fills the login screen for all users
  - Each user authenticates with their own Firefly III account via OAuth

### AppFlowy

- Multi-container: postgres (pgvector), redis, minio, gotrue, appflowy-cloud, appflowy-web, admin-frontend, nginx
- `GOTRUE_JWT_SECRET` must be at least 32 chars and identical across gotrue and appflowy-cloud: `openssl rand -hex 32`
- MinIO bucket `appflowy` is created automatically by the `appflowy-minio-setup` one-shot container
- Admin UI at `https://appflowy.yourdomain.com/web/` (manage users, workspaces)
- GoTrue auth at `https://appflowy.yourdomain.com/gotrue/`
- Desktop/mobile clients connect directly to `https://appflowy.yourdomain.com`

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

### Beszel

- Two containers: `beszel` (hub, web UI) and `beszel-agent` (monitors this host)
- Admin account created on first browser visit
- `beszel-agent` uses `network_mode: host` (not the `homeserver` network) so it can report real host network throughput
- Agent crash-loops on first start (`Failed to load public keys`) until paired — after first hub login: hub UI → add a system (or Settings → Tokens for a universal token), then set `BESZEL_AGENT_TOKEN` / `BESZEL_AGENT_KEY` in `beszel/.env` and `sh homeserver.sh dev up beszel`
- Reports Docker container stats too via the mounted `${DOCKER_SOCKET}`

---

[← New Services](10-new-services.md) | [Home](../setup.md)
