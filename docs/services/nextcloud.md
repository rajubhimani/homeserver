# Nextcloud

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** File storage + sharing, replaces Google Drive.
**Port:** `8081` (host) → `80` (container) | **Data:** entirely named volumes now — `nextcloud-html`/`nextcloud-config`/`nextcloud-data`/`nextcloud-custom-apps`/`nextcloud-postgres-alpine` (see below for why; nothing left under `service_data/data/nextcloud/` needs browsing directly) | **Requires:** Postgres + Redis | **Memory:** DB capped 512M in compose.yml; app: no hard limit set; measured idle ~181MB total (app 122 + db 21 + redis 6 + cron 31) — comfortably within Nextcloud's own official guidance (128MB min / 512MB recommended per PHP-FPM process, though their docs note actual needs scale with users/apps/file volume)
**Pinned versions (as of this pass):** `nextcloud:34.0.3` (app + cron), `postgres:18.4-alpine` (db), `redis:8.10-alpine` (cache/locking). All facts below are checked against Nextcloud 34's own current documentation, not general/older Nextcloud knowledge.

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

## Automated family app setup

```bash
uv run services/nextcloud/configure-family-apps.py
```

Installs and enables the apps a family actually uses (Files, Calendar, Contacts, Talk, Mail, Deck, Whiteboard, Office/ONLYOFFICE) and wires up [ONLYOFFICE](onlyoffice.md)/[Whiteboard](whiteboard.md)/[ClamAV](clamav.md) integration automatically if those services are set up (reads their JWT secrets straight from their own `.env` files — nothing to copy-paste by hand) — unconditionally, no prompt, since that part is unambiguous setup work.

It then **prints the full list** of enterprise/business-bundle apps that ship by default but add nothing for personal use (workflow automation, retention policies, LDAP/SAML, social-media sharing, the global lookup directory, etc. — see "Enterprise app cleanup" below) with a one-line reason each, and **asks for confirmation** before touching any of it — answer no, or run it non-interactively without `--yes`, and that whole step is skipped while everything else still applies. Pass `--yes`/`-y` to skip the prompt and apply the cleanup immediately. Reproduces the exact app configuration this deployment settled on after evaluating the full default app list against actual family usage (Drive + Talk + Calendar replacement, not a business/team instance).

Pass `--list`/`-l` to just print what's currently installed (grouped into Family / Enterprise-bundle-candidate / Other-core, each with live enabled/disabled state) without taking any action — useful to check current state before deciding whether to run the cleanup.

Safe to re-run any time — every step is idempotent (install-if-missing, set-if-different, disable-if-enabled), including re-running just to reconsider the cleanup prompt later. Requires Nextcloud to already be past its own first-run setup wizard (needs a working `occ`); the script checks this itself and tells you plainly if it isn't ready yet.

### Enterprise app cleanup — what's disabled/removed and why

Nextcloud ships (and its app-store "bundles" install) a lot of apps aimed at businesses/teams/compliance that a family Drive+Talk+Calendar replacement has no use for. `configure-family-apps.py` removes or disables all of these — none of it is needed, and some of it is a real liability if left on unconfigured:

- **`terms_of_service`, `support`** — enterprise onboarding consent flow and a "buy Nextcloud GmbH support" upsell app. Not applicable to a private instance.
- **`socialsharing_diaspora`/`facebook`/`twitter`/`email`** — social-media share buttons on files. Irrelevant to a private instance.
- **`survey_client`** — sends anonymous usage telemetry back to Nextcloud. Disabled for privacy, no functional loss.
- **`lookup_server_connector`** (can't be removed/disabled, it's shipped/core) — publishes any profile field a user sets to "Published" scope to Nextcloud's **global public user directory**. Neutralized at the actual control point instead: `config:system:set lookup_server --value ""` in `config.php`, which disables the publishing behavior regardless of the app's own disable state.
- **`files_confidential`, `files_retention`, `files_automatedtagging`, `workflowengine`** — enterprise compliance tooling (marking files "confidential," auto-deleting files by retention policy, automated tagging rules). `files_retention` specifically is worth removing rather than ignoring — a retention policy could **auto-delete family files** if one were ever configured, even accidentally. `workflowengine` itself can't be removed (shipped/core) but is inert with the rule-producing apps gone.
- **`files_downloadlimit`** — caps download counts on share links; a business use case (limiting client access to a shared invoice), not a family one.
- **`user_ldap`, `user_saml`** — enterprise SSO backends. Nothing in this stack uses either.
- **`webhook_listeners`** — lets other apps register webhooks off Nextcloud events; a dev/automation feature, unused here.
- **`nextcloud_announcements`** — official Nextcloud marketing broadcasts (distinct from `announcementcenter`, which is local/admin-authored and left enabled).
- **`groupfolders`, `circles`, `tables`, `forms`, `collectives`, `cloud_federation_api`, `related_resources`** — team/org sharing constructs, a mini-spreadsheet app, a form builder, team wiki pages, and cross-instance federation — none of which a small family sharing files/calendars with each other needs. `cloud_federation_api` can't be disabled (shipped/core) but sits dormant since nothing federates with this instance.
- **`integration_forgejo_gitea`** — Forgejo notification/link-preview integration. A real, working feature, but one that only benefits whoever personally uses Forgejo, not the family — removed as a deliberate scope call, not because it's broken. Re-add with `occ app:install integration_forgejo_gitea` if wanted later; nothing else depends on it.

**A few apps couldn't be removed even though they're disabled** — Nextcloud marks `support`, `survey_client`, `files_downloadlimit`, `user_ldap`, `webhook_listeners`, `nextcloud_announcements`, `circles`, `related_resources` as shipped/core, so `occ app:remove` refuses (`"is a shipped/core app and cannot be removed"`). Disabled means none of their code runs — no functional or privacy exposure — just a small amount of disk space that can't be reclaimed since Nextcloud treats them as part of its own core distribution, not separately-installed apps.

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

**External storage doesn't reliably self-detect new files just from browsing the folder in the web UI**, despite `filesystem_check_changes` being enabled by default — confirmed after repointing `OS_ISO_ROOT` at a new host path: the files existed on disk and the mount tested green, but nothing showed up until a manual `occ files:scan` ran. This now self-heals automatically — see `nextcloud-cron`'s dual responsibility under "Architecture notes" below. If you add another external storage mount that's large (thousands of files), reconsider the blanket `--all` scan — scope it to a path/user instead so the cron doesn't get expensive.

## Create Family Accounts

```text
Top right avatar → Administration → Users → New User
```

One account per family member. They log in via the same URL you use.

## Making devices actually use it

Every family member's account (above) needs to actually be connected from their own devices — the web UI alone doesn't sync anything locally. Confirmed live against [nextcloud.com/install](https://nextcloud.com/install/#install-clients) and Nextcloud 34's own [Desktop Client user manual](https://docs.nextcloud.com/server/34/user_manual/en/desktop/installation.html) — not assumed from memory. Could not actually install any of these apps myself (no phone/desktop to test against this instance); the steps below are transcribed from Nextcloud's own current docs, not independently confirmed end-to-end.

- **Desktop sync client (Windows/macOS/Linux):** download from [nextcloud.com/install](https://nextcloud.com/install/#install-clients) — current build at time of writing is **34.0.2** (Windows `.msi`, macOS `.pkg` for macOS 13+, Linux AppImage; distro packages also listed on that page). Windows/macOS: run the installer and follow its wizard. Linux: add the distro repo listed on that same page, install the signing key, then install via your package manager (or just use the AppImage) — and make sure a keyring (GNOME Keyring or KWallet) is running, or the client can't store the login. First run of the setup wizard asks for the **server address** — enter the same URL used in a browser, e.g. `https://nextcloud.yourdomain.com` — then opens a browser tab to log in and grant access, then a local-folder screen to sync everything or pick individual folders before clicking **Connect**. Runs in the background afterward, syncing both directions. Each client release supports the latest three stable server major versions at the time it was built, so client `34.0.2` against this stack's pinned server `34.0.3` is squarely inside that window (matching major version) — keep the client reasonably current rather than assuming forward compatibility indefinitely.
- **Mobile app (Android/iOS):** install "Nextcloud" (package `com.nextcloud.client`) — Android via [Google Play](https://play.google.com/store/apps/details?id=com.nextcloud.client) or [F-Droid](https://f-droid.org/packages/com.nextcloud.client/), iOS via the [App Store](https://apps.apple.com/us/app/nextcloud/id1125420102). Same pattern as the desktop client: enter the server address (`https://nextcloud.yourdomain.com`), it opens a browser to log in and grant access, then you land in the app. Turn on auto-upload for photos/videos in the app's own settings if you want camera-roll backup this way — Immich is this stack's dedicated photo tool, but Nextcloud's auto-upload works too if you'd rather keep everything in one place.
- **WebDAV (any third-party file manager/client that isn't the official app):** point it at `https://nextcloud.yourdomain.com/remote.php/dav/files/<username>/` (that exact path — not just the bare domain, which is only what the *official* clients auto-discover). Use an **app password** for this rather than the real account password: avatar menu → **Settings** → **Security** (left sidebar) → **Devices & sessions** → generate a new app password at the bottom, and give it a name so it's identifiable later if you need to revoke it. Nextcloud's own docs note this is both more secure (revocable without changing the main password) and noticeably faster for WebDAV specifically than the primary password.

## Using it day to day

Confirmed against Nextcloud's own current user manual, not assumed from memory.

- **Sharing links:** in **Files**, hover a file/folder → the **Share** icon → **Create link**. This generates a public URL (`https://nextcloud.yourdomain.com/s/<token>`). Folder links can be set to **Read only**, **Allow upload and editing**, **File drop** (others can upload without seeing existing contents), **Hide download**, password-protected, and given an expiration date after which the link auto-disables. Sharing directly with another user/group on this instance (instead of a public link) uses the same Share panel — pick their name instead of "create link" — and their access level is adjustable there too.
- **Installing apps (Calendar, Contacts, etc.):** top-right avatar menu → **Apps** → browse or search by name → **Enable**. Nextcloud pulls the app from its app store and installs it if it isn't bundled already. Enabled apps then show up in the top app-switcher bar next to Files — this is the same mechanism used for "External storage support" above.

## Health endpoint

`compose.yml`'s healthcheck runs `curl -f http://localhost/status.php` inside the `nextcloud` container every 30s (10s timeout, 5 retries, 60s start period). Confirmed live on this instance (`docker exec nextcloud curl -s http://localhost/status.php`):

```json
{"installed":true,"maintenance":false,"needsDbUpgrade":false,"version":"34.0.3.2","versionstring":"34.0.3","edition":"","productname":"Nextcloud","extendedSupport":false}
```

`installed`/`maintenance`/`needsDbUpgrade` are the fields that actually matter for health — `curl -f` just checks for a non-error HTTP status, so a `200` with `"maintenance":true` still reports "healthy" to Docker even though the app is refusing normal requests (see the maintenance-mode troubleshooting section below, which checks this endpoint's near-neighbor `occ status` for exactly that reason). `versionstring` matches the pinned image tag (`34.0.3`) as expected.

## Architecture notes

- Uses **partial volume mounts** (`config`, `data`, `custom_apps`) — do **not** mount the full `/var/www/html`
- `nextcloud/hooks/before-starting/00-sync-php.sh` runs `rsync` on every startup to populate PHP files into the partial mount
- `nextcloud/hooks/before-starting/02-configure-proxy.sh` runs `occ config:system:set` for `trusted_proxies`, `trusted_domains`, `overwriteprotocol`, and `overwrite.cli.url` on **every** startup (skipped only pre-install) — this is why those don't need to be set manually and won't drift even if `DOMAIN`/network config changes later. If you ever need a value this hook doesn't set (e.g. a raw Tailscale IP in `trusted_domains` for IP-only access with no domain), edit that script directly — a one-off `docker exec ... occ config:system:set` gets silently overwritten by the hook on the next restart.
- **`nextcloud-cron` has two responsibilities, not one** — its entrypoint loop (`compose.yml`) runs `cron.php` (Nextcloud's own background jobs: notifications, previews, housekeeping — the reason this container exists at all) *and* `occ files:scan --all` (external storage rescan — added because `filesystem_check_changes` doesn't reliably pick up new files on the `OS_ISO_ROOT` mount from browsing alone; see "Enable External Storage" above), back-to-back, every `CRON_SCAN_INTERVAL_SECONDS` (`.env`, default `300` = 5 minutes). It mounts `OS_ISO_ROOT` read-only for the scan step — `USER_DATA_ROOT`/`/mnt/seagate` is deliberately commented out here since nothing currently needs cron to rescan it, only the app container. If you add another external storage mount that should also self-heal this way, mount it here too and it rides the same loop. **Raise this interval if `OS_ISO_ROOT` sits on a slow or shared disk** — see `docs/services/jellyfin.md`'s playback-buffering troubleshooting entry for the general pattern (slow/FUSE-mounted storage, or contention with another service sharing the same physical disk).

## Troubleshooting: unhealthy / 503 / redirect loops behind the proxy

Symptom: Nextcloud thinks every request is plain HTTP even though Cloudflare/nginx terminates HTTPS in front of it — manifests as unhealthy status, 503s, redirect loops, or broken links.

**Check first:** is `02-configure-proxy.sh` (above) actually running? `docker exec nextcloud php occ config:system:get overwriteprotocol` should print `https`. If it prints something else or errors, the hook didn't run (e.g. hooks volume not mounted, script not executable) — fix that rather than patching `config.php` by hand, since a manual fix won't survive the hook overwriting it on the next restart.

## Troubleshooting: landing page shows Nextcloud unhealthy but the container looks fine

Nextcloud validates the `Host` header against `trusted_domains` on **every** request, including health-check probes. If `landing/nginx.conf`'s `/health/nextcloud` block ever regresses to a bare `proxy_pass http://nextcloud:80/;` (no `Host` override), every probe arrives with an untrusted `Host` and gets rejected with a 400 — showing up as a stream of 400s in Nextcloud's access log from the *proxy's* IP, easy to mistake for a performance/DB problem when it's actually just the health check itself being wrong.

**Fix:** the health check must hit `/status.php` (the same lightweight endpoint Nextcloud's own Docker healthcheck uses) with `proxy_set_header Host localhost;` explicitly set.

**General lesson for any service's `/health/<service>` block:** if the app validates the `Host` header (trusted domains/allowed hosts/CSRF origin checks — Nextcloud, and potentially others), a bare `proxy_pass $upstream/;` health check will silently 400 forever; explicitly set `proxy_set_header Host localhost;` (or whatever the app trusts) on that specific location block.

## Troubleshooting: stuck in maintenance mode / every request 503s after an update

Symptom: `docker exec nextcloud php occ status` shows `maintenance: true` and `needsDbUpgrade: true`, every request (web UI, desktop/mobile clients, `status.php`) returns `503`, and this persists across container/host restarts instead of resolving itself.

**Cause:** `compose.yml` pins the image to the floating tag `nextcloud:34`, not an exact point release. Any `dev update` (or a recreate that re-pulls that tag) can silently jump point releases — Docker Hub keeps moving `34` to whatever the newest `34.x.y` build is. On startup the official image's entrypoint auto-detects the version bump and runs `occ upgrade` itself, no confirmation, no staging. If that upgrade's DB migration fails partway, maintenance mode is left on and every subsequent container restart just retries (and re-fails) the same migration — it does not fix itself.

**Check the actual failure** in the non-access-log lines of `docker logs nextcloud` (the access log dominates the tail, so grep it out):

```bash
docker logs nextcloud 2>&1 | grep -viE '^\S+ - \S+ \[.*"(GET|POST|PROPFIND|PUT|HEAD|OPTIONS|DELETE|MKCOL|REPORT|UNLOCK|LOCK)'
```

Look for `Exception: Database error when running migration ... Update failed`.

**Root cause hit here:** `SQLSTATE[42501]: Insufficient privilege: must be owner of table oc_calendars_federated`. This is the `oc_admin` ownership split again (see "Migrated: `nextcloud-db`..." below) — `config.php`'s `dbuser` is `oc_admin`, but every table and sequence in the database (152 tables, 124 sequences at the time) was owned by role `nextcloud` instead. `oc_admin` had DML grants (SELECT/INSERT/UPDATE/DELETE) but not ownership, which is all normal app usage needs — so this sat latent until an upgrade's migration needed `ALTER TABLE`, which requires ownership.

**Fix:** reassign ownership of every table and sequence to `oc_admin`, then restart so the upgrade hook retries:

```bash
# snapshot first — this runs a real schema migration
docker exec nextcloud-db pg_dump -U nextcloud -d nextcloud > nextcloud_pre_upgrade_fix.sql

docker exec nextcloud-db psql -U nextcloud -d nextcloud -t -c "
SELECT 'ALTER TABLE ' || quote_ident(tablename) || ' OWNER TO oc_admin;' FROM pg_tables WHERE schemaname='public' AND tableowner='nextcloud'
UNION ALL
SELECT 'ALTER SEQUENCE ' || quote_ident(sequencename) || ' OWNER TO oc_admin;' FROM pg_sequences WHERE schemaname='public' AND sequenceowner='nextcloud';
" > reassign.sql
docker cp reassign.sql nextcloud-db:/tmp/reassign.sql
docker exec nextcloud-db psql -U nextcloud -d nextcloud -f /tmp/reassign.sql

docker restart nextcloud
```

Note plain `REASSIGN OWNED BY nextcloud TO oc_admin;` does **not** work here — it errors with `cannot reassign ownership of objects owned by role nextcloud because they are required by the database system`, because `nextcloud` also owns the database itself. Generating explicit `ALTER TABLE`/`ALTER SEQUENCE` statements sidesteps that. This is safe to run live: the `nextcloud` role is itself a Postgres superuser, so it keeps full access to everything regardless of object ownership (needed for `pg_dump`/backups) — reassigning objects to `oc_admin` doesn't take anything away from it.

After the restart, `occ status` should show `needsDbUpgrade: false`, but the upgrade hook has been observed to print `Update successful` and then still leave `maintenance: true` — check and clear it explicitly:

```bash
docker exec -u www-data nextcloud php occ maintenance:mode --off
```

**To stop this from recurring:** `compose.yml` is now pinned to the exact tag `nextcloud:34.0.3` (was the floating `nextcloud:34`) — bump it deliberately rather than letting `dev update` silently jump point releases.

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

## Fixed: `files_antivirus` was configured for a `clamscan` binary that doesn't exist — now backed by a real [ClamAV](clamav.md) service

**Symptom:** file operations that trigger an antivirus scan failed with a `500` — `Exception: RuntimeException ... files_antivirus/lib/Scanner/LocalClam.php ... The antivirus executable could not be found at /usr/bin/clamscan`. First caught via [Whiteboard](whiteboard.md)'s auto-save silently failing every 10-20s (see that doc's "Fixed: whiteboard content wasn't actually saving" entry) — this app blocked *any* scan-triggering write, not just whiteboard.

**Root cause:** `occ config:list files_antivirus` showed `av_path: /usr/bin/clamscan` — a path to a local binary expected to exist **inside the `nextcloud` container itself**, not a separate service. The stock `nextcloud` image doesn't ship ClamAV, and no separate ClamAV container existed anywhere in this stack — so the app was enabled but non-functional from the start.

**Interim fix (now superseded):** `occ app:disable files_antivirus` — stopped the write-blocking failures while a real backend was set up.

**Real fix:** added a standalone [ClamAV](clamav.md) service (same pattern as [ONLYOFFICE](onlyoffice.md)/[Whiteboard](whiteboard.md)) and reconfigured `files_antivirus` to daemon mode:

```bash
docker exec -u www-data nextcloud php occ app:enable files_antivirus
docker exec -u www-data nextcloud php occ config:app:set files_antivirus av_mode --value="daemon"
docker exec -u www-data nextcloud php occ config:app:set files_antivirus av_host --value="clamav"
docker exec -u www-data nextcloud php occ config:app:set files_antivirus av_port --value="3310"
```

Confirmed actually working via `occ files_antivirus:test` (not just "container healthy") — see `docs/services/clamav.md` for the full verification, the `av_infected_action=only_log` reasoning, and an important gotcha: scanning is **background/queued, not synchronous on upload** — a real EICAR test upload produced zero scan activity until `occ files_antivirus:background-scan` was run (or the regular `nextcloud-cron` job cycle reaches it), which looked like a silent failure before that was understood.

## Migrated: `nextcloud-db` from `postgres:18.4` to `postgres:18.4-alpine`

Via `uv run homeserver.py dev dump nextcloud` + `dev migrate nextcloud` — see `docs/services/forgejo.md`'s "Migrated: forgejo-db..." section for the full process and general gotchas.

**Nextcloud-specific gotcha hit here:** `config.php`'s `dbuser` was `oc_admin`, a role Nextcloud's own installer created ad-hoc at some point — separate from `.env`'s `POSTGRES_USER=nextcloud`, which is what actually connects during setup/backup operations. A per-database `pg_dump` never captures roles (they're cluster-wide), so after the first restore attempt `oc_admin` didn't exist in the fresh cluster and Nextcloud crash-looped on `SQLSTATE[08006]: password authentication failed for user "oc_admin"`. This is exactly why `dump` also runs `pg_dumpall --roles-only` and `migrate` applies it before the main restore — confirm your own `config.php`'s `dbuser` matches what you expect before assuming a migration here is done, since the container can come up "healthy" on the DB-ping healthcheck while still crash-looping on this.

**Second round, same incident:** the first fix (creating `oc_admin` via the roles dump) was necessary but not sufficient on its own — the restore also ran with `--no-privileges`, which skips the dump's captured `GRANT` statements entirely. That meant `oc_admin` could log in but had zero table privileges (`SQLSTATE[42501]: permission denied for table oc_appconfig`), since `pg_restore` connects and creates everything as `POSTGRES_USER` (`nextcloud`), not `oc_admin`. `--no-privileges` was the wrong fix for the original error — the actual fix was sequencing (apply roles *before* the restore, which was already correct), so once that ordering is right the dump's own `GRANT ... TO oc_admin` statements succeed naturally and `--no-privileges` isn't needed at all. Removed it; `pg_restore` now runs with `--no-owner --clean --if-exists` only. Re-verified end-to-end from a fresh plain-Postgres baseline afterward with zero manual steps needed.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
