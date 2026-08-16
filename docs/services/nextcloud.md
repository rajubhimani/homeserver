# Nextcloud

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** File storage + sharing, replaces Google Drive.
**Port:** `8081` (host) → `80` (container) | **Data:** entirely named volumes now — `nextcloud-html`/`nextcloud-config`/`nextcloud-data`/`nextcloud-custom-apps`/`nextcloud-postgres` (see below for why; nothing left under `service_data/data/nextcloud/` needs browsing directly) | **Requires:** Postgres + Redis | **Memory:** DB capped 512M in compose.yml; app: no hard limit set; measured idle ~685MB total (app 612 + db 35 + redis 16 + cron 22) — comfortably within Nextcloud's own official guidance (128MB min / 512MB recommended per PHP-FPM process, though their docs note actual needs scale with users/apps/file volume)

## Setup

```bash
cp services/nextcloud/.env.example services/nextcloud/.env
```

Edit `services/nextcloud/.env`:

```env
USER_DATA_ROOT=/mnt/seagate
OS_ISO_ROOT=/mnt/os-iso

# Postgres
POSTGRES_DB=nextcloud
POSTGRES_USER=nextcloud
POSTGRES_PASSWORD=your_strong_password

# Nextcloud admin
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=your_strong_password
```

**Admin password in `.env` must not contain `$`** — Docker Compose interprets `$VAR` patterns as variable references and silently mangles passwords containing `$`. Use `openssl rand -hex 20` to generate a safe password.

```bash
uv run homeserver.py dev up nextcloud
```

**Access:** Cloudflare path `https://nextcloud.yourdomain.com` | Tailscale path `http://100.x.x.x:8081` — login with your admin credentials.

## Enable External Storage

```text
Apps → search "External storage support" → Enable

Settings → Administration → External Storage → Add Storage
  Folder name: Seagate
  Storage type: Local
  Configuration: /mnt/seagate
  Available for: All users
→ click checkmark (green = working)
```

`OS_ISO_ROOT` (mounted at `/mnt/os-iso`) works the same way — add a second External Storage entry pointing at that path if you want the ISO folder browsable in Nextcloud too.

## Create Family Accounts

```text
Top right avatar → Administration → Users → New User
```

One account per family member. They log in via the same URL you use.

## Architecture notes

- Uses **partial volume mounts** (`config`, `data`, `custom_apps`) — do **not** mount the full `/var/www/html`
- `nextcloud/hooks/before-starting/00-sync-php.sh` runs `rsync` on every startup to populate PHP files into the partial mount
- `nextcloud/hooks/before-starting/02-configure-proxy.sh` runs `occ config:system:set` for `trusted_proxies`, `trusted_domains`, `overwriteprotocol`, and `overwrite.cli.url` on **every** startup (skipped only pre-install) — this is why those don't need to be set manually and won't drift even if `DOMAIN`/network config changes later. If you ever need a value this hook doesn't set (e.g. a raw Tailscale IP in `trusted_domains` for IP-only access with no domain), edit that script directly — a one-off `docker exec ... occ config:system:set` gets silently overwritten by the hook on the next restart.

## Troubleshooting: unhealthy / 503 / redirect loops behind the proxy

Symptom: Nextcloud thinks every request is plain HTTP even though Cloudflare/nginx terminates HTTPS in front of it — manifests as unhealthy status, 503s, redirect loops, or broken links.

**Check first:** is `02-configure-proxy.sh` (above) actually running? `docker exec nextcloud php occ config:system:get overwriteprotocol` should print `https`. If it prints something else or errors, the hook didn't run (e.g. hooks volume not mounted, script not executable) — fix that rather than patching `config.php` by hand, since a manual fix won't survive the hook overwriting it on the next restart.

## Troubleshooting: landing page shows Nextcloud unhealthy but the container looks fine

Nextcloud validates the `Host` header against `trusted_domains` on **every** request, including health-check probes. If `landing/nginx.conf`'s `/health/nextcloud` block ever regresses to a bare `proxy_pass http://nextcloud:80/;` (no `Host` override), every probe arrives with an untrusted `Host` and gets rejected with a 400 — showing up as a stream of 400s in Nextcloud's access log from the *proxy's* IP, easy to mistake for a performance/DB problem when it's actually just the health check itself being wrong.

**Fix:** the health check must hit `/status.php` (the same lightweight endpoint Nextcloud's own Docker healthcheck uses) with `proxy_set_header Host localhost;` explicitly set.

**General lesson for any service's `/health/<service>` block:** if the app validates the `Host` header (trusted domains/allowed hosts/CSRF origin checks — Nextcloud, and potentially others), a bare `proxy_pass $upstream/;` health check will silently 400 forever; explicitly set `proxy_set_header Host localhost;` (or whatever the app trusts) on that specific location block.

## Why `html`/`config`/`data`/`custom_apps` are named volumes, not bind mounts

Nextcloud enforces two checks a Windows bind mount can't reliably satisfy — see the `homeserver-postgres` skill for the general Windows-`chown`-reliability caveat this is an instance of:

1. **`config.php` must be owned by `www-data` (UID 33).** If `chown` fails on the bind mount, install/upgrade loops forever on `Console has to be executed with the user that owns the file config/config.php` ("Retrying install...").
2. **`data/` must be group-accessible but not world-readable** (`chmod 0770`). If ownership is stuck wrong (per #1), no combination of permission bits gives `www-data` access without also being world-readable — which Nextcloud refuses to start with anyway.

Named volumes sidestep both checks entirely (daemon-managed, no host-filesystem ownership translation). **Trade-off:** `data/` (your actual files) is no longer directly browsable from Windows Explorer — only through the Nextcloud web UI/app, same as any NAS.

**Migrating existing bind-mounted data into a named volume** (e.g. moving an install from Linux/Mac onto Windows):

```bash
docker volume create nextcloud_nextcloud-config
docker run --rm -v "<old-config-dir>:/from:ro" -v nextcloud_nextcloud-config:/to alpine:3.24.1 sh -c "cp -a /from/. /to/ && chown -R 33:33 /to"
# repeat for data (nextcloud_nextcloud-data) and html (nextcloud_nextcloud-html)
```

## Migrated: `nextcloud-db` from `postgres:18.4` to `postgres:18.4-alpine`

Via `uv run homeserver.py dev dump nextcloud` + `dev migrate nextcloud` — see `docs/services/forgejo.md`'s "Migrated: forgejo-db..." section for the full process and general gotchas.

**Nextcloud-specific gotcha hit here:** `config.php`'s `dbuser` was `oc_admin`, a role Nextcloud's own installer created ad-hoc at some point — separate from `.env`'s `POSTGRES_USER=nextcloud`, which is what actually connects during setup/backup operations. A per-database `pg_dump` never captures roles (they're cluster-wide), so after the first restore attempt `oc_admin` didn't exist in the fresh cluster and Nextcloud crash-looped on `SQLSTATE[08006]: password authentication failed for user "oc_admin"`. This is exactly why `dump` also runs `pg_dumpall --roles-only` and `migrate` applies it before the main restore — confirm your own `config.php`'s `dbuser` matches what you expect before assuming a migration here is done, since the container can come up "healthy" on the DB-ping healthcheck while still crash-looping on this.

**Second round, same incident:** the first fix (creating `oc_admin` via the roles dump) was necessary but not sufficient on its own — the restore also ran with `--no-privileges`, which skips the dump's captured `GRANT` statements entirely. That meant `oc_admin` could log in but had zero table privileges (`SQLSTATE[42501]: permission denied for table oc_appconfig`), since `pg_restore` connects and creates everything as `POSTGRES_USER` (`nextcloud`), not `oc_admin`. `--no-privileges` was the wrong fix for the original error — the actual fix was sequencing (apply roles *before* the restore, which was already correct), so once that ordering is right the dump's own `GRANT ... TO oc_admin` statements succeed naturally and `--no-privileges` isn't needed at all. Removed it; `pg_restore` now runs with `--no-owner --clean --if-exists` only. Re-verified end-to-end from a fresh plain-Postgres baseline afterward with zero manual steps needed.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
