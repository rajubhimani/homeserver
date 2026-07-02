# 10 — New Services

[← Firewall](09-firewall.md) | [Home](../setup.md)

---

All services follow the same three-file compose pattern:

- `compose.yml` — base config, no ports
- `compose.dev.yml` — ports on all interfaces (direct access)
- `compose.prod.yml` — ports on `127.0.0.1` only (reverse proxy handles external)
- `.env` — secrets and paths (copy from `.env.example`)

Use `homeserver.sh` to manage them (see [Maintenance](08-maintenance.md)).
New services always go into `SERVICES_EXTRA` in `homeserver.sh` first.

---

## Jellyfin

**Purpose:** Stream movies, TV shows, and music from your server.
**Port:** `8096` | **Data:** `service_data/jellyfin/`

```bash
cp jellyfin/.env.example jellyfin/.env
# set MEDIA_ROOT to your media drive path
sh homeserver.sh dev up jellyfin
```

| Method | How |
| --- | --- |
| First visit | Open `http://<ip>:8096` — setup wizard creates the admin account |

---

## Vaultwarden

**Purpose:** Self-hosted password manager (Bitwarden-compatible).
**Port:** `8200` | **Data:** `service_data/vaultwarden/`

```bash
cp vaultwarden/.env.example vaultwarden/.env
# set ADMIN_TOKEN (openssl rand -base64 48)
sh homeserver.sh dev up vaultwarden
```

| Method | How |
| --- | --- |
| Admin panel | `http://<ip>:8200/admin` → enter `ADMIN_TOKEN` |

Signups disabled by default. Invite users via the admin panel → Users → Invite.

---

## Paperless-ngx

**Purpose:** Scan, OCR, and archive documents with full-text search.
**Port:** `8010` | **Data:** `service_data/paperless/` | **Requires:** Postgres + Redis

```bash
cp paperless/.env.example paperless/.env
# set POSTGRES_PASSWORD, PAPERLESS_SECRET_KEY, PAPERLESS_ADMIN_USER/PASSWORD
sh homeserver.sh dev up paperless
```

| Method | How |
| --- | --- |
| Env vars ✓ | `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` — auto-created on first start |
| CLI | `docker exec -it paperless python manage.py createsuperuser` |

---

## Stirling PDF Lite

**Purpose:** Lightweight PDF toolkit — always in `SERVICES_EXTRA`.
**Port:** `8090` | **Image:** `stirlingtools/stirling-pdf:latest-ultra-lite`

```bash
cp stirling-pdf-lite/.env.example stirling-pdf-lite/.env
sh homeserver.sh dev up stirling-pdf-lite
```

| Method | How |
| --- | --- |
| Env vars ✓ | `STIRLING_ADMIN_USER` / `STIRLING_ADMIN_PASSWORD` — set at startup |

---

## Stirling PDF Full

**Purpose:** Full PDF toolkit with OCR and LibreOffice conversion.
**Port:** `8089` | **Image:** `stirlingtools/stirling-pdf:latest` (~1.5 GB RAM)

> Not in `all` — start manually when needed, stop when done.

```bash
sh homeserver.sh dev up stirling-pdf
sh homeserver.sh dev down stirling-pdf
```

---

## Mealie

**Purpose:** Recipe manager and meal planner.
**Port:** `9925` | **Data:** `service_data/mealie/` | **Requires:** Postgres

```bash
cp mealie/.env.example mealie/.env
# set POSTGRES_PASSWORD
sh homeserver.sh dev up mealie
```

| Method | How |
| --- | --- |
| Default credentials | `changeme@example.com` / `MyPassword` — **change immediately** |

---

## Forgejo

**Purpose:** Community-driven Git hosting — repos, issues, pull requests, CI/CD (Actions).
**Port:** `3002` (web), `2223` (SSH) | **Data:** `service_data/forgejo/` | **Requires:** Postgres

```bash
cp forgejo/.env.example forgejo/.env
# set POSTGRES_PASSWORD, FORGEJO_DOMAIN, FORGEJO_ROOT_URL
sh homeserver.sh dev up forgejo
```

| Method | How |
| --- | --- |
| CLI ✓ | `docker exec -it forgejo forgejo admin user create --username admin --password yourpassword --email admin@example.com --admin` |

**Actions runner (optional):**

```bash
sh homeserver.sh dev up forgejo --profile runner
docker exec -it forgejo-runner forgejo-runner register
```

---

## GitLab CE

**Purpose:** Full DevOps platform — Git, CI/CD, registry, issue tracking.
**Port:** `8085` (web), `2224` (SSH) | **Data:** `service_data/gitlab/` | **Requires:** ~4 GB RAM

```bash
cp gitlab/.env.example gitlab/.env
# set GITLAB_HOSTNAME, GITLAB_EXTERNAL_URL
sh homeserver.sh dev up gitlab
```

GitLab takes 2–3 minutes to fully start on first launch.

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:8085` — set `root` password on first login |
| CLI | `docker exec -it gitlab gitlab-rake "gitlab:password:reset[root]"` |

**Runner (optional):**

```bash
sh homeserver.sh dev up gitlab --profile runner
docker exec -it gitlab-runner gitlab-runner register
```

---

## Uptime Kuma

**Purpose:** Monitor services and alert when something goes down.
**Port:** `3001` | **Data:** `service_data/uptime-kuma/`

```bash
cp uptime-kuma/.env.example uptime-kuma/.env
sh homeserver.sh dev up uptime-kuma
```

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:3001` — create admin account on first launch |

---

## Dozzle

**Purpose:** Real-time Docker container log viewer in the browser.
**Port:** `9999`

```bash
sh homeserver.sh dev up dozzle
```

No login by default — restrict via nginx access control if exposed publicly.

---

## Stalwart Mail

**Purpose:** All-in-one mail server — SMTP, IMAP, and admin UI.
**Port:** `8091` (admin/web) | **Data:** `service_data/stalwart/`
**Other ports:** `25` (SMTP), `587` (submission), `143` (IMAP), `993` (IMAPS)

```bash
cp stalwart/.env.example stalwart/.env
# set STALWART_PUBLIC_URL=https://mail.yourdomain.com
sh homeserver.sh dev up stalwart
```

Run the setup wizard at `http://<ip>:8091` on first start.

Set up DNS records for email to work externally:

- `MX` → `mail.yourdomain.com`
- `SPF` TXT → `v=spf1 mx ~all`
- `DMARC` TXT → `v=DMARC1; p=quarantine`
- `DKIM` — generated by Stalwart admin → copy the TXT record

---

## Snappymail

**Purpose:** Fast, lightweight webmail client.
**Port:** `8097` | **Data:** `service_data/snappymail/`

```bash
cp snappymail/.env.example snappymail/.env
sh homeserver.sh dev up snappymail
```

| Method | How |
| --- | --- |
| Admin panel | `http://<ip>:8097/?admin` — set `SNAPPYMAIL_ADMIN_PASSWORD` in `.env` first |

Configure IMAP/SMTP in the admin panel: IMAP → `stalwart:143`, SMTP → `stalwart:587`.

---

## Roundcube

**Purpose:** Full-featured webmail with plugins, address book, and calendar.
**Port:** `8098` | **Data:** `service_data/roundcube/`

```bash
cp roundcube/.env.example roundcube/.env
# set ROUNDCUBEMAIL_DEFAULT_HOST=stalwart, ROUNDCUBEMAIL_SMTP_SERVER=stalwart
sh homeserver.sh dev up roundcube
```

Login with your IMAP credentials. No separate admin account — all config via `.env`.

---

## Syncthing

**Purpose:** Peer-to-peer file sync between devices, no cloud required.
**Port:** `8087` | **Data:** `service_data/syncthing/`

```bash
cp syncthing/.env.example syncthing/.env
sh homeserver.sh dev up syncthing
```

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:8087` — set a password immediately in Settings → GUI |

Add remote devices by sharing Device IDs. Add folders to sync.

---

## Authentik

**Purpose:** Identity provider — SSO, OAuth2, OIDC, SAML for all services.
**Port:** `8088` | **Data:** `service_data/authentik/` | **Requires:** Postgres + Redis

```bash
cp authentik/.env.example authentik/.env
# generate: openssl rand -hex 32 → AUTHENTIK_SECRET_KEY
# set POSTGRES_PASSWORD
sh homeserver.sh dev up authentik
```

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:8088/if/admin/` — set password for `akadmin` |

---

## Ntfy

**Purpose:** Push notifications to phone/desktop via simple HTTP requests.
**Port:** `8092` | **Data:** `service_data/ntfy/`

```bash
cp ntfy/.env.example ntfy/.env
sh homeserver.sh dev up ntfy
```

Send a notification:

```bash
curl -d "Backup complete" https://ntfy.yourdomain.com/my-topic
```

Install the Ntfy app on your phone and subscribe to your topic.

---

## Miniflux

**Purpose:** Minimal, fast RSS reader with keyboard shortcuts.
**Port:** `8093` | **Data:** `service_data/miniflux/` | **Requires:** Postgres

```bash
cp miniflux/.env.example miniflux/.env
# set ADMIN_USERNAME, ADMIN_PASSWORD, POSTGRES_PASSWORD
sh homeserver.sh dev up miniflux
```

| Method | How |
| --- | --- |
| Env vars ✓ | `ADMIN_USERNAME` / `ADMIN_PASSWORD` — created on first start |

---

## Audiobookshelf

**Purpose:** Audiobook and podcast server with mobile app.
**Port:** `8094` | **Data:** `service_data/audiobookshelf/`

```bash
cp audiobookshelf/.env.example audiobookshelf/.env
# set AUDIOBOOKS_PATH and PODCASTS_PATH to your media locations
sh homeserver.sh dev up audiobookshelf
```

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:8094` — create admin account on first launch |

Connect the Audiobookshelf mobile app to `https://audiobookshelf.yourdomain.com`.

---

## Conduit (Matrix)

**Purpose:** Lightweight Matrix homeserver for self-hosted chat.
**Port:** `8095` (client), `8448` (federation) | **Data:** `service_data/conduit/`

```bash
cp conduit/.env.example conduit/.env
sh homeserver.sh dev up conduit
```

To create first accounts, temporarily set `ALLOW_REGISTRATION=true` in `conduit/.env`,
restart, register accounts, then set it back to `false`.

Connect with any Matrix client (Element, FluffyChat) to `https://conduit.yourdomain.com`.

> Conduit uses a distroless image — no shell available inside the container.

---

## OpenProject

**Purpose:** Project management with Gantt charts, wikis, and issue tracking.
**Port:** `8099` | **Data:** `service_data/openproject/` | **Requires:** ~2 GB RAM (bundled Postgres)

```bash
cp openproject/.env.example openproject/.env
# generate: openssl rand -hex 64 → SECRET_KEY_BASE
sh homeserver.sh dev up openproject
```

| Method | How |
| --- | --- |
| Default credentials | `admin` / `admin` — **change immediately** on first login |

---

## Plane

**Purpose:** Open-source issue tracker and project management.
**Port:** `8100` | **Data:** `service_data/plane/` | **Requires:** ~4 GB RAM

```bash
cp plane/.env.example plane/.env
# generate: openssl rand -hex 32 → SECRET_KEY
# set POSTGRES_PASSWORD, RABBITMQ passwords, MINIO credentials
sh homeserver.sh dev up plane
```

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:8100` — create workspace and admin account |

---

## InvoiceShelf

**Purpose:** Open-source invoicing and billing (community successor to Crater — same codebase, same DB schema).
**Port:** `8101` | **Data:** `service_data/invoiceshelf/` | **Requires:** MariaDB

```bash
cp invoiceshelf/.env.example invoiceshelf/.env
# generate: echo "base64:$(openssl rand -base64 32)" → APP_KEY
# set MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD
sh homeserver.sh dev up invoiceshelf
```

| Method | How |
| --- | --- |
| Setup wizard ✓ | Browse to `http://<ip>:8101` — wizard creates admin account |

---

## AppFlowy

**Purpose:** Open-source Notion alternative — docs, databases, kanban, and AI writing tools.
**Port:** `8103` | **Data:** `service_data/appflowy/` | **Requires:** ~2 GB RAM

```bash
cp appflowy/.env.example appflowy/.env
# generate: openssl rand -hex 32 → GOTRUE_JWT_SECRET
# set POSTGRES_PASSWORD and MINIO_ROOT_PASSWORD
mkdir -p service_data/appflowy/{postgres,redis,minio}
sh homeserver.sh dev up appflowy
```

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:8103` — create account and workspace |
| Admin UI | `http://<ip>:8103/web/` — manage users and workspaces |

> The `appflowy-minio-setup` container runs once to create the `appflowy` S3 bucket, then exits. This is normal.

### Compatible image versions

All services below must stay in sync. `appflowy_web` uses its own versioning scheme — `0.15.5` is the current latest for the web frontend regardless of cloud version.

| Service | Image | Version | Notes |
| --- | --- | --- | --- |
| Cloud backend | `appflowyinc/appflowy_cloud` | `0.16.5` | Must match gotrue/admin |
| Auth service | `appflowyinc/gotrue` | `0.16.5` | Must match cloud/admin |
| Admin UI | `appflowyinc/admin_frontend` | `0.16.5` | Must match cloud/gotrue |
| Web frontend | `appflowyinc/appflowy_web` | `0.15.5` | Own versioning scheme — nginx rewrite handles path differences |
| Database | `pgvector/pgvector` | `pg16` | — |
| Cache | `redis` | `7-alpine` | — |

> **WebSocket path difference:** `appflowy_web:0.15.5` sends WebSocket requests to `/ws/{workspace_id}/` but `appflowy_cloud:0.16.x` changed to `/ws/v2/{workspace_id}`. The internal nginx (`appflowy/nginx.conf`) rewrites the path automatically.

### Known issues and fixes

**"Database error finding user" on signup**

GoTrue and AppFlowy Cloud both query their tables without a schema prefix, but the tables live in the `auth` schema. The database role needs `search_path=auth,public`. This is handled automatically by `appflowy/postgres-init/init.sh` on first DB initialization.

**Migration tracking split — applies when upgrading or after container recreation on an existing DB:**

AppFlowy uses two migration trackers:

| Service | Tracking table | Schema |
| --- | --- | --- |
| GoTrue | `schema_migrations` | `auth` (pre-seeded 55 rows) and `public` (full 70 rows) |
| AppFlowy Cloud | `_sqlx_migrations` | `auth` (pre-seeded 8 rows) and `public` (full 144 rows) |

After setting `search_path=auth,public` on an existing DB, both services find the incomplete `auth.*` tables first and try to re-run already-applied migrations → GoTrue fails with `column "client_id" does not exist`, AppFlowy Cloud fails with `trigger "af_workspace_after_insert" already exists`.

**Fix:** Sync both migration tables, then restart:

```bash
docker exec appflowy-db psql -U appflowy -d appflowy -c "
INSERT INTO auth.schema_migrations (version)
SELECT version FROM public.schema_migrations
WHERE version NOT IN (SELECT version FROM auth.schema_migrations);

INSERT INTO auth._sqlx_migrations (version, description, installed_on, success, checksum, execution_time)
SELECT version, description, installed_on, success, checksum, execution_time
FROM public._sqlx_migrations
WHERE version NOT IN (SELECT version FROM auth._sqlx_migrations);
"
docker restart appflowy-gotrue appflowy-cloud
```

**Full data wipe and fresh start:**

```bash
sh homeserver.sh prod down appflowy
sudo rm -rf ~/homeserver/service_data/appflowy/
mkdir -p ~/homeserver/service_data/appflowy/{postgres,redis,minio}
sh homeserver.sh prod up appflowy
```

After a clean wipe the `postgres-init/init.sh` runs automatically on DB first boot, sets search_path, and everything works without manual steps.

---

## Firefly III

**Purpose:** Personal finance manager — income, expenses, budgets, accounts, recurring transactions.
**Port:** `8102` | **Data:** `service_data/firefly/`

```bash
cp firefly/.env.example firefly/.env
# APP_KEY: openssl rand -hex 16  (exactly 32 chars)
# STATIC_CRON_TOKEN: openssl rand -hex 16  (exactly 32 chars)
# set POSTGRES_PASSWORD and SITE_OWNER
mkdir -p service_data/firefly/postgres
mkdir -p service_data/firefly/storage/{framework/{cache/data,sessions,views},logs,app/public,upload}
sh homeserver.sh dev up firefly
# One-time: seed OAuth keys into persistent storage (required on first start)
docker exec -it firefly php artisan passport:install --force   # Docker
podman exec -it firefly php artisan passport:install --force   # Podman
# Keys are created as root — make them readable by www-data (PHP process)
chmod 644 service_data/firefly/storage/oauth-private.key service_data/firefly/storage/oauth-public.key
```

| Method | How |
| --- | --- |
| First user ✓ | Browse to `http://<ip>:8102` — first registration becomes admin |
| Disable signups | Firefly III → Administration → `/settings/configuration` |

> **OAuth keys** are stored in `service_data/firefly/storage/` and persist across restarts — `passport:install --force` only needs to be run once on the very first start. After that, restarts never regenerate the keys, so existing sessions and JWTs stay valid. Running `--force` again will rotate the keys and log everyone out.
> ```bash
> # Docker
> docker exec -it firefly php artisan passport:install --force
> # Podman
> podman exec -it firefly php artisan passport:install --force
> ```

### Data Importer

**Port:** `8104` | Starts automatically with Firefly

One-time setup after Firefly III is running:

1. Firefly III → Profile → OAuth → **OAuth Clients** → Create new client
2. Redirect URL: `https://firefly-import.yourdomain.com/callback` — uncheck "Keep a secret?"
3. Copy the resulting **Client ID** (a UUID like `019f0fc9-379d-73bf-bc43-7ec7c6fb4ac9`)
4. Set `FIREFLY_III_CLIENT_ID=<uuid>` in `firefly/.env` and restart the importer:
   ```bash
   sh homeserver.sh prod up firefly
   ```

This pre-fills the Client ID for all users. Each user then authenticates with their own Firefly III account via OAuth — no shared token needed.

Browse to `https://firefly-import.yourdomain.com` to import CSV, YNAB exports, or connect bank accounts via Nordigen.

---

## Beszel

**Purpose:** Lightweight server monitoring — CPU, memory, disk, network, and Docker container stats with alerts.
**Port:** `8106` | **Data:** `service_data/beszel/`

```bash
cp beszel/.env.example beszel/.env
sh homeserver.sh dev up beszel
```

Two containers start: `beszel` (hub, web UI) and `beszel-agent` (monitors this host). The agent **crash-loops** until it has a token/key pair from the hub — this is expected (`restart: unless-stopped` just keeps retrying) and stops once you pair it below.

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:8106` — create admin account on first launch |
| Pair the agent | Hub UI → **Add System** (or **Settings → Tokens** for a universal token) → copy the token + public key |

After pairing:

```bash
# beszel/.env
BESZEL_AGENT_TOKEN=<token from hub>
BESZEL_AGENT_KEY=<public key from hub>
```

```bash
sh homeserver.sh dev up beszel
```

The system indicator in the hub UI turns green once the agent connects.

> `beszel-agent` runs with `network_mode: host` instead of joining the `homeserver` network — this is required for it to report real host-level network throughput rather than just its own virtual interface. It mounts `${DOCKER_SOCKET}` read-only to also report per-container stats.

---

[← Firewall](09-firewall.md) | [Home](../setup.md)
