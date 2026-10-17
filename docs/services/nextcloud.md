# Nextcloud

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** File storage + sharing, replaces Google Drive.
**Port:** `8081` (host) → `80` (container) | **Data:** entirely named volumes — `nextcloud-html`/`nextcloud-config`/`nextcloud-data`/`nextcloud-custom-apps`/`nextcloud-postgres-alpine` (see below for why; nothing under `service_data/data/nextcloud/` needs browsing directly). **Apps in use:** Files and the default apps, plus ONLYOFFICE, Whiteboard and Files Antivirus. Nothing else is installed (no Talk, Calendar, Contacts, Mail or Deck). | **Requires:** Postgres + Redis | **Memory:** DB capped 512M in compose.yml; app: no hard limit set; measured idle ~181MB total (app 122 + db 21 + redis 6 + cron 31) — comfortably within Nextcloud's own official guidance (128MB min / 512MB recommended per PHP-FPM process, though their docs note actual needs scale with users/apps/file volume)
**Pinned versions (as of this pass):** `nextcloud:35.0.2` (app + cron), `postgres:18.6-alpine` (db), `valkey/valkey:9.1.2-alpine` (cache/locking; Valkey, the Redis-protocol drop-in that AWS and GCP run, since 2026-10-03, [managed-cloud parity](../10-new-services.md#managed-cloud-parity-orchestrators-and-backing-services)). Fresh install of 35.0.2 on 2026-10-17 (see "Fresh start on 35.0.2" below). Apps: `files_antivirus` 6.5.0, `onlyoffice` 10.2.1, `whiteboard` 2.0.0 (checked against the App Store's NC35 listing).

## Setup

```bash
cp services/nextcloud/.env.example services/nextcloud/.env
```

Edit `services/nextcloud/.env`:

```env
# Postgres
POSTGRES_DB=nextcloud
POSTGRES_USER=nextcloud
POSTGRES_PASSWORD=your_strong_password

# Nextcloud admin
NEXTCLOUD_ADMIN_USER=your_username
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

Installs and enables the only apps this install uses on top of Nextcloud's defaults (Whiteboard, ONLYOFFICE, Files Antivirus) and wires up [ONLYOFFICE](onlyoffice.md)/[Whiteboard](whiteboard.md)/[ClamAV](clamav.md) integration automatically if those services are set up (reads their JWT secrets straight from their own `.env` files — nothing to copy-paste by hand) — unconditionally, no prompt, since that part is unambiguous setup work.

It then walks through the enterprise/business-bundle apps that ship by default but add nothing for personal use (workflow automation, retention policies, LDAP/SAML, social-media sharing, the global lookup directory, etc. — see "Enterprise app cleanup" below) with a one-line reason each, and asks **how** to apply the cleanup:

```text
Apply how? [a]ll at once / [o]ne by one / [n]o, skip:
```

- **`a`** — every app in the list gets removed/disabled, same as the old bulk behavior.
- **`o`** — goes through each app individually (`Remove? [y/N]:`), so you can keep something you'd actually use (e.g. `forms` for family polls) while dropping the rest.
- **`n`** — skips this whole step, nothing touched. Everything else (family apps, ONLYOFFICE/Whiteboard/ClamAV wiring) still runs regardless of this choice.

After choosing `a` or `o`, it asks `Save this selection for next time? [y/N]:` — answering yes writes it to `services/nextcloud/family-apps-selection.json` (gitignored, local to this install — matches the repo's existing blanket `*.json` rule, no `.env`-style secret in it, just per-app keep/remove decisions). Answering no just finishes, nothing written.

**On a later run**, if a saved selection exists:
- **Interactively**, it's offered first — `Reuse it, or start fresh? [r]euse / [f]resh:` — reusing applies it immediately with no further prompts.
- **Non-interactively** (`--yes`, or no TTY at all — e.g. a scripted fresh install) it's applied **automatically**, no flags needed beyond having saved it once. This is deliberate: a saved selection means you already decided, and completing that "reproducible fresh install" loop without re-asking is the actual point of this script. With no saved selection, `--yes` falls back to the full bulk list (today's original behavior); no `--yes` and no TTY stays a safe no-op, same as before saved-selection support existed.
- Pass **`--fresh`** to ignore any saved selection and decide from scratch (interactively) or fall back to the full bulk list (with `--yes`) — useful to force a clean reset without deleting the JSON file by hand.

Pass `--list`/`-l` to just print what's currently installed (grouped into Family / Enterprise-bundle-candidate / Other-core, each with live enabled/disabled state, annotated with `(saved: keep|remove)` if a selection was saved) without taking any action — useful to check current state before deciding whether to run the cleanup.

Safe to re-run any time — every step is idempotent (install-if-missing, set-if-different, disable-if-enabled, remove-if-already-removed), including re-running just to reconsider the cleanup choice later. Requires Nextcloud to already be past its own first-run setup wizard (needs a working `occ`); the script checks this itself and tells you plainly if it isn't ready yet.

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

## External storage

Not used. The `/mnt/seagate` and `/mnt/os-iso` mounts, the `OS_ISO_ROOT`/`USER_DATA_ROOT` settings and the cron `files:scan --all` loop were removed on 2026-10-17 with the fresh start. To add a mount again, add the volume to `nextcloud` in `compose.yml`, enable **External storage support**, and add the folder under **Administration → External Storage**. External mounts don't reliably self-detect new files, so a scheduled `occ files:scan` for that path would be needed too.

## Create Family Accounts

```text
Top right avatar → Administration → Users → New User
```

One account per family member. They log in via the same URL you use.

## Making devices actually use it

Every family member's account (above) needs to actually be connected from their own devices — the web UI alone doesn't sync anything locally. Confirmed live against [nextcloud.com/install](https://nextcloud.com/install/#install-clients) and Nextcloud 34's own [Desktop Client user manual](https://docs.nextcloud.com/server/34/user_manual/en/desktop/installation.html) — not assumed from memory. Could not actually install any of these apps myself (no phone/desktop to test against this instance); the steps below are transcribed from Nextcloud's own current docs, not independently confirmed end-to-end.

- **Desktop sync client (Windows/macOS/Linux):** download from [nextcloud.com/install](https://nextcloud.com/install/#install-clients) — current build at time of writing is **34.0.2** (Windows `.msi`, macOS `.pkg` for macOS 13+, Linux AppImage; distro packages also listed on that page). Windows/macOS: run the installer and follow its wizard. Linux: add the distro repo listed on that same page, install the signing key, then install via your package manager (or just use the AppImage) — and make sure a keyring (GNOME Keyring or KWallet) is running, or the client can't store the login. First run of the setup wizard asks for the **server address** — enter the same URL used in a browser, e.g. `https://nextcloud.yourdomain.com` — then opens a browser tab to log in and grant access, then a local-folder screen to sync everything or pick individual folders before clicking **Connect**. Runs in the background afterward, syncing both directions. Each client release supports the latest three stable server major versions at the time it was built, so client `34.0.2` against this stack's pinned server `34.0.4` is squarely inside that window (matching major version) — keep the client reasonably current rather than assuming forward compatibility indefinitely.
- **Mobile app (Android/iOS):** install "Nextcloud" (package `com.nextcloud.client`) — Android via [Google Play](https://play.google.com/store/apps/details?id=com.nextcloud.client) or [F-Droid](https://f-droid.org/packages/com.nextcloud.client/), iOS via the [App Store](https://apps.apple.com/us/app/nextcloud/id1125420102). Same pattern as the desktop client: enter the server address (`https://nextcloud.yourdomain.com`), it opens a browser to log in and grant access, then you land in the app. Turn on auto-upload for photos/videos in the app's own settings if you want camera-roll backup this way — Immich is this stack's dedicated photo tool, but Nextcloud's auto-upload works too if you'd rather keep everything in one place.
- **WebDAV (any third-party file manager/client that isn't the official app):** point it at `https://nextcloud.yourdomain.com/remote.php/dav/files/<username>/` (that exact path — not just the bare domain, which is only what the *official* clients auto-discover). Use an **app password** for this rather than the real account password: avatar menu → **Settings** → **Security** (left sidebar) → **Devices & sessions** → generate a new app password at the bottom, and give it a name so it's identifiable later if you need to revoke it. Nextcloud's own docs note this is both more secure (revocable without changing the main password) and noticeably faster for WebDAV specifically than the primary password.

## Using it day to day

Confirmed against Nextcloud's own current user manual, not assumed from memory.

- **Sharing links:** in **Files**, hover a file/folder → the **Share** icon → **Create link**. This generates a public URL (`https://nextcloud.yourdomain.com/s/<token>`). Folder links can be set to **Read only**, **Allow upload and editing**, **File drop** (others can upload without seeing existing contents), **Hide download**, password-protected, and given an expiration date after which the link auto-disables. Sharing directly with another user/group on this instance (instead of a public link) uses the same Share panel — pick their name instead of "create link" — and their access level is adjustable there too.
- **Installing apps (Calendar, Contacts, etc.):** top-right avatar menu → **Apps** → browse or search by name → **Enable**. Nextcloud pulls the app from its app store and installs it if it isn't bundled already. Enabled apps then show up in the top app-switcher bar next to Files — this is the same mechanism used for "External storage support" above.

## Health endpoint

`compose.yml`'s healthcheck runs `curl -f http://localhost/status.php` inside the `nextcloud` container every 30s (10s timeout, 5 retries, 60s start period). Confirmed live on this instance (`docker exec nextcloud curl -s http://localhost/status.php`):

```json
{"installed":true,"maintenance":false,"needsDbUpgrade":false,"version":"35.0.2.2","versionstring":"35.0.2","edition":"","productname":"Nextcloud","extendedSupport":false}
```

`installed`/`maintenance`/`needsDbUpgrade` are the fields that actually matter for health — `curl -f` just checks for a non-error HTTP status, so a `200` with `"maintenance":true` still reports "healthy" to Docker even though the app is refusing normal requests (see the maintenance-mode troubleshooting section below, which checks this endpoint's near-neighbor `occ status` for exactly that reason). `versionstring` matches the pinned image tag (`35.0.2`) as expected.

## Architecture notes

- **Database login comes from `.env`:** `config/db.config.php` sets `dbhost`/`dbname`/`dbuser`/`dbpassword` from `POSTGRES_*`. It follows the image's own `redis.config.php`/`smtp.config.php` pattern; Nextcloud merges every `*.config.php` over `config.php`. Without it Nextcloud would log in as the `oc_<admin>` role its installer wrote into `config.php`, which exists only in that one database server (the cause of the ownership and migration problems recorded below, and of the Kubernetes import failure). Moving the database (a managed Postgres, or Kubernetes) is a `.env` change. **How it gets into `config/`:** the file is mounted *outside* the Nextcloud tree (`/usr/src/homeserver/db.config.php`) and `hooks/before-starting/00-install-db-config.sh` copies it into `config/` on every start. It must not be mounted straight into `config/` (see "Fresh start on 35.0.2").
- Hook scripts must be executable in git (`git update-index --chmod=+x` / `git add --chmod=+x`). The image skips a hook without the executable flag (`... was skipped, because it lacks the executable flag`); two were stored without it in the past (fixed 2026-10-04). Hooks run as `www-data`, not root.
- Uses **partial volume mounts** (`config`, `data`, `custom_apps`) — do **not** mount the full `/var/www/html`
- `nextcloud/hooks/before-starting/00-sync-php.sh` runs `rsync` on every startup to populate PHP files into the partial mount
- `nextcloud/hooks/before-starting/02-configure-proxy.sh` runs `occ config:system:set` for `trusted_proxies`, `trusted_domains`, `overwriteprotocol`, and `overwrite.cli.url` on **every** startup (skipped only pre-install) — this is why those don't need to be set manually and won't drift even if `DOMAIN`/network config changes later. If you ever need a value this hook doesn't set (e.g. a raw Tailscale IP in `trusted_domains` for IP-only access with no domain), edit that script directly — a one-off `docker exec ... occ config:system:set` gets silently overwritten by the hook on the next restart.
- **`nextcloud-cron`** runs `cron.php` (Nextcloud's own background jobs: notifications, previews, housekeeping, the antivirus background scan) every `CRON_INTERVAL_SECONDS` (`.env`, default `300`). It shares the `nextcloud` container's volumes, including `config/`, so it gets `db.config.php` from the hook above without its own mount.

## Real client IPs

- **Nextcloud itself** (brute-force protection, `nextcloud.log` `remoteAddr`) uses `X-Forwarded-For` from the trusted proxies in `TRUSTED_PROXIES`, and logs the real IP under both runtimes.
- **Apache's access log:** `config/remoteip.conf` replaces the image's `remoteip.conf`, which read `X-Real-IP`. It reads `X-Forwarded-For` and walks it from the right past the internal proxies (`mod_remoteip`), so the access log shows the real IP. A faked `X-Forwarded-For` doesn't fool it. Verified 2026-10-04.

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

**To stop this from recurring:** `compose.yml` is pinned to an exact tag (was the floating `nextcloud:34`; now `nextcloud:35.0.2`) — bump it deliberately rather than letting `dev update` silently jump point releases.

## Upgrading safely (pre-flight checklist)

**The ownership split regresses** — found again on 2026-09-28 (152 tables / 124 sequences back under `nextcloud`, alongside ~126/112 under `oc_admin`), most likely from a later dump/restore or migrate that recreated objects as `POSTGRES_USER`. So check it before *every* image bump, not just once:

```bash
docker exec nextcloud-db psql -U nextcloud -d nextcloud -tAc \
  "select tableowner,count(*) from pg_tables where schemaname='public' group by 1"
```

Anything other than a single `oc_admin|<n>` row → run the reassign fix from the section above (it's safe live) before bumping the tag. Then:

1. `uv run homeserver.py prod dump nextcloud` (logical dump + roles — runs live, no restart). Add `uv run homeserver.py prod backup nextcloud` (cold snapshot of every volume) **only if `occ status` shows `needsDbUpgrade: false`** — `backup` stops and restarts the container, and the image's entrypoint runs `occ upgrade` on its own at startup whenever an upgrade is pending. That's exactly how the 2026-09-28 outage started: a pending calendar 6.5.4 → 6.6.1 migration ran unattended during a backup restart, hit the ownership split, and left the instance in maintenance mode.
2. If `occ status` already shows `needsDbUpgrade: true` (e.g. an app auto-updated), run `docker exec -u www-data nextcloud php occ upgrade` on the *current* image first, so the image bump isn't also carrying someone else's pending migration. **`occ upgrade` also pulls every available app update from the App Store** (`Update app <x> from App Store` in its output) — including major bumps you might have wanted to hold. Run `occ app:update --showonly` first so there are no surprises, and check anything with a paired external service (see whiteboard below).
3. Bump both `nextcloud` and `nextcloud-cron` image tags together, then `uv run homeserver.py prod update nextcloud`.
4. Verify: `occ status` shows `maintenance: false` and `needsDbUpgrade: false`, and `versionstring` matches the new tag.

### Updating apps (without a server bump)

Same ownership check and `prod dump` first. Then update one app at a time from the CLI (not the web UI — it can time out mid-migration and doesn't show the real error), checking status between each:

```bash
docker exec -u www-data nextcloud php occ app:update --showonly
docker exec -u www-data nextcloud php occ app:update <app>
docker exec -u www-data nextcloud php occ status   # maintenance: false, needsDbUpgrade: false
```

Avoid `app:update --all`. Treat a major version as its own planned change. **`whiteboard` must stay in lockstep with the separate [Whiteboard](whiteboard.md) backend image** — bump `services/whiteboard/compose.yml` in the same pass (done for 1.5.9 → 2.0.0 on 2026-09-28). If an update fails: read the error (so far it has always been ownership), fix it, then `occ upgrade` + `occ maintenance:mode --off`; the dump is the fallback.

**Only move up one major version at a time** (Nextcloud doesn't support skipping majors). Nextcloud 35 had been on hold since 2026-09-28 (open schema-drift reports after 34.0.4 → 35.0.0 involving `oc_talk_*`/`oc_mail_*` tables, [server#64505](https://github.com/nextcloud/server/issues/64505), [server#64590](https://github.com/nextcloud/server/issues/64590)). It was revisited at 35.0.2 and installed fresh on 2026-10-17, without Talk or Mail, so those reports don't apply. See "Fresh start on 35.0.2" below.

**Sandbox trial, 2026-09-30 (34.0.4 → 35.0.1)** — a full clone of the old instance was upgraded in an isolated sandbox (removed on 2026-10-02; recover it from git history at commit `bc16144`). Findings, kept for reference if a major upgrade is ever done in place again: the upgrade aborts with `HMAC does not match` until `notifications.webpush_vapid_privkey`/`..._pubkey` are removed from `oc_appconfig`; it disables `spreed`, `deck` and `quota_warning` as incompatible; `occ db:schema:check` then reports Mail-index and `oc_federated_invites` differences that are checker-side (NC35's own `DropFederatedInvitesTable` migration drops that table on purpose).

## Fresh start on 35.0.2 (2026-10-17)

**Why:** a stuck `cron.php` ran at about 96% CPU for 11 hours (load average 8). It was the Files Antivirus background scan (`OCA\Files_Antivirus\BackgroundJob\BackgroundScanner`), and the cause was data missing from disk. Two accounts (`admin`, `Neeraj Badal`) still had 64 file rows each in `oc_filecache`, but their data folders were gone from the `nextcloud-data` volume (`files:scan` reported "User folder … exists in cache but not on disk"). Those rows were never scanned, so the scanner picked them first, tried to open a file that wasn't there, and spun. It reproduced by hand: `occ files_antivirus:scan` on one of those paths pinned a core and ignored `timeout`'s TERM signal. ClamAV was healthy throughout (PING/VERSION answered, `files_antivirus:test` passed). The exact line where it spins wasn't traced; files_antivirus 6.5.0 (released 2026-10-16) has no changelog entry about it.

**What was done:** snapshot (`service_data/backup/nextcloud/`), `pg_dump`, a verified plain-file copy of `rajubhimani`'s 177 files (`pre-fresh-start-files-20261017/`), then `prod reset nextcloud`, a blank 35.0.2, the app script, and the files copied back into the new account's data folder followed by `occ files:scan rajubhimani` (177 files, 0 errors). `files_antivirus:background-scan` then scanned all 173 non-empty files in 90 s with exit 0. Lost on purpose: the two orphaned accounts, shares, version history, trash, and the Talk/Mail/Deck/Calendar/Contacts apps (all test-only).

**Gotcha found and fixed — fresh install failed with `Cannot write into "config" directory!`:** on a blank volume the image seeds and chowns `config/` only while it is empty (`directory_empty` in its entrypoint). The old setup mounted `db.config.php` straight into `config/`, which made it non-empty, so `config/` stayed root-owned and the installer could not write `config.php`. The setup worked before only because the volumes already existed. It had been broken for any blank start since the file mount was added on 2026-10-04, so the 2026-10-03 "fresh-install verification" below predates it. Hooks can't fix it (the image runs them as `www-data`), and an init container would work but adds a service. Upstream's own approach — custom `*.config.php` files may be added to `config/`, hooks run before start — is followed instead: the file is mounted outside the tree and copied in by `00-install-db-config.sh`. Verified with `prod reset nextcloud` from blank: no error, `config/` seeded with the image's default config files, `db.config.php` in place, `occ status` clean.

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


## Fresh-install verification (2026-10-03)

Reset to an empty install, came up healthy, then restored from its `reset-backup-*` snapshot and came up healthy again: installed state, users, the `/OS-ISOs` external storage and the OnlyOffice connection restored. Procedure: [16 — MIN/CORE reset runbook](../16-min-core-reset-runbook.md).

## Reverse proxy: no buffering (2026-10-11)

The `nextcloud` block in `services/nginx-plain/templates/default.conf.template` sets `proxy_buffering off;` and `proxy_request_buffering off;`. Large downloads and previews were buffered to disk by nginx-plain, and uploads (up to `client_max_body_size 10G`) were buffered in full before reaching Nextcloud. Same fix as Jellyfin's playback hangs (see [jellyfin.md](jellyfin.md)). Apply with `docker restart nginx-plain`, since the template is rendered at container start.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
