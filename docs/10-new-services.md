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

## Gitea

**Purpose:** Self-hosted Git — repos, issues, pull requests, CI/CD.
**Port:** `3000` (web), `2222` (SSH) | **Data:** `service_data/gitea/` | **Requires:** Postgres

```bash
cp gitea/.env.example gitea/.env
# set POSTGRES_PASSWORD, GITEA_DOMAIN, GITEA_ROOT_URL
sh homeserver.sh dev up gitea
```

| Method | How |
| --- | --- |
| CLI ✓ | `docker exec -it gitea gitea admin user create --username admin --password yourpassword --email admin@example.com --admin` |

**Actions runner (optional):**

1. Site Admin → Runners → Create Runner → copy token
2. Set `GITEA_RUNNER_TOKEN=<token>` in `.env`
3. `sh homeserver.sh dev up gitea --profile runner`

---

## Forgejo

**Purpose:** Community-driven Gitea fork — same UX, independent release cycle.
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
# edit conduit/conduit.toml — set server_name to matrix.yourdomain.com
sh homeserver.sh dev up conduit
```

To create first accounts, temporarily set `allow_registration = true` in `conduit.toml`,
restart, register accounts, then set it back to `false`.

Connect with any Matrix client (Element, FluffyChat) to `https://matrix.yourdomain.com`.

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

## Crater

**Purpose:** Open-source invoicing and billing.
**Port:** `8101` | **Data:** `service_data/crater/` | **Requires:** MariaDB

```bash
cp crater/.env.example crater/.env
# generate: echo "base64:$(openssl rand -base64 32)" → APP_KEY
# set MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD
sh homeserver.sh dev up crater
```

| Method | How |
| --- | --- |
| Setup wizard ✓ | Browse to `http://<ip>:8101` — wizard creates admin account |

---

[← Firewall](09-firewall.md) | [Home](../setup.md)
