# Immich

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Photo management, replaces Google Photos.
**Port:** `2283` (host) → `2283` (container, `immich-server`) | **Requires:** Postgres (custom pgvector build) + Redis | **Memory:** DB capped 2G in compose.yml (raised from 512M — see incident below); app/ml/redis: no hard limit set; measured idle ~531MB total across all 5 containers (server 501 + ml 12 + redis 4 + db 14 + offline-remover <1). Immich's own docs state 6GB minimum / 8GB recommended for the full stack with ML enabled, and explicitly recommend **at least 2GB for Postgres** if a Docker memory limit is set on it at all

## Setup

```bash
cp services/immich/.env.example services/immich/.env
```

Edit `services/immich/.env`:

```env
UPLOAD_LOCATION=../../service_data/media/immich
# Postgres data lives in a named Docker volume (declared in compose.yml), not
# a bind mount — no path to set here. Back it up with
# `uv run homeserver.py <env> backup immich`.

# Generate with: openssl rand -hex 32
IMMICH_SECRET=your_hex_secret_here

# Postgres
DB_PASSWORD=your_strong_password
DB_USERNAME=immich
DB_DATABASE_NAME=immich
DB_URL=postgresql://immich:your_strong_password@immich-database:5432/immich
```

**`DB_URL` must use `immich-database` as the hostname — not `localhost`.**

```bash
uv run homeserver.py dev up immich
```

**Access:** Cloudflare path `https://immich.yourdomain.com` or `https://photos.yourdomain.com` | Tailscale path `http://100.x.x.x:2283`

## First login

Admin account is created on first browser visit — no env var needed. Immich does not support creating the admin account via env vars.

## Machine Learning

Enables facial recognition and smart search. `immich-ml` is a normal, always-included service now (no `profiles:` gate) — `up immich` starts it automatically. In UI: `Admin → Machine Learning → toggle on → Save`, then run initial jobs under `Admin → Jobs`: Smart Search → Run All, Face Detection → Run All.

**To exclude it** (low-resource setups that don't want the RAM/CPU cost): `uv run homeserver.py dev up immich --no-ml` — starts every other immich container but scales `immich-machine-learning` to 0 replicas, so no container gets created for it at all. This only affects `up`; `down`/`backup`/`update immich` always act on the whole project regardless.

## Mobile App Setup

Install the **Immich** app (Android / iOS — free). Server URL by access path:

- Cloudflare: `https://immich.yourdomain.com`
- Tailscale: `http://100.x.x.x:2283` — only works while connected to the tailnet; the Cloudflare path works anywhere

Not independently confirmed live (no phone was used to install/log into the app for this pass) — the rest of this section is Immich's own current mobile-app documentation, not training-memory guesswork.

**Login:** enter the server URL above. If login instead fails with **"Your app major version is not compatible with the server!"**, this is Immich's mobile app enforcing a real runtime major-version check against the server (confirmed via Immich's own GitHub issue tracker) — see the version-compatibility note below before troubleshooting anything else.

**Enabling backup:**

1. Tap the cloud icon in the top-right corner to open the backup screen.
2. Select which album(s) on the device to back up — Immich auto-detects common source folders (Camera, Screenshots, WhatsApp Images, Downloads, etc.) and each gets its own toggle; double-tap an album to exclude it instead.
3. Scroll to the bottom and tap **Enable Backup**.

**Network/background behavior (defaults, changeable in the backup settings screen):**

- Wi-Fi only by default — uploading a large existing library over mobile data first is not recommended unless this is deliberately turned off.
- **iOS:** background uploads require **Settings (the iOS Settings app, not Immich's) → General → Background App Refresh** enabled for the Immich app, or backup only proceeds while the app is open in the foreground.
- **Android:** the app exposes its own toggle to restrict background uploads to only run while charging, plus a minimum-delay setting for how long after a photo is taken the background upload task is allowed to run. Aggressive OEM battery optimization (common on some Android skins) can still kill the background worker regardless of these toggles — if backups stall with the app closed, check the phone's per-app battery/background-activity restriction setting too.
- **Album sync:** a separate feature from picking which local albums to back up — under **Library → On this device**, syncing keeps a chosen device album's membership mirrored to an Immich album server-side, rather than just uploading the files into one flat timeline.

**Version compatibility — checked specifically for the pinned `v3.1.0` server:** Immich's mobile app enforces a **major-version match** against the server at login/sync time, not just a soft recommendation — an app still on a `v2.x.x` build cannot talk to this stack's `v3.1.0` server at all (confirmed via Immich's own upgrade docs and multiple GitHub issues describing the exact "app major version is not compatible" error). Update the mobile app to a current `v3.x.x` build before or immediately after any server major-version bump; minor/patch bumps (e.g. this repo's pin of `v3.1.0` moving to a later `v3.x.x`) don't have this constraint.

## Using it day to day

Confirmed against Immich's own current documentation, not assumed from memory.

- **Albums:** select one or more photos/videos → the album icon (or **+**) → create a new album or add to an existing one. Albums are the main way to group a trip/event across what auto-backup otherwise dumps into one flat timeline.
- **Sharing an album:** open the album → **Share** → choose which users on this instance can see it, as either **Editor** (can add their own photos/videos to it) or **Viewer** (read-only). A **public link** is the other option — generates a URL anyone can open without an account, with its own settings for an expiration date, password, whether downloads are allowed, and whether metadata is shown.
- **Partner sharing:** distinct from album sharing — **Account Settings → Partner Sharing** shares your *entire* library (not just one album) with another user of your choice, who can then view and download everything, not just a curated subset.
- **Smart search:** the search bar takes natural-language queries ("dog on a beach") thanks to the CLIP model `immich-ml` runs — no manual tagging needed for this to work, since `immich-ml` is always-on in this stack (no profile gate, see Setup above). Narrow further with explicit filters in the same search: by person/face, city/state/country (reverse-geocoded from GPS), camera make/model, file name or folder path, date range, media type, star rating, or OCR'd text found in the image itself. The underlying CLIP model is swappable under **Administration → Settings → Machine Learning Settings → Smart Search** if search quality/speed needs tuning for a particular language mix.
- **People:** **Explore → People** lists everyone Face Detection has clustered (see the Machine Learning jobs above) — name a person once and their photos become searchable/filterable by name across the whole library.

## Health endpoint

`immich-server` and `immich-ml` both ship a Docker-image-baked `HEALTHCHECK` (not declared in this repo's `compose.yml` — inherited from the upstream image, confirmed via `docker inspect immich-server`/`immich-ml --format '{{json .Config.Healthcheck}}'`, which show `immich-healthcheck` and `python3 healthcheck.py` respectively rather than a plain HTTP probe). Confirmed live against the running `v3.1.0` containers:

```bash
docker exec immich-server curl -s http://localhost:2283/api/server/ping
# {"res":"pong"}  — HTTP 200
docker exec immich-server curl -s http://localhost:2283/api/server/version
# {"major":3,"minor":1,"patch":0,"prerelease":null}
```

`immich-db` and `immich-redis` use plain compose-level healthchecks instead (`pg_isready` and `valkey-cli ping`, both visible directly in `compose.yml`). All five containers (`immich-server`, `immich-ml`, `immich-db`, `immich-redis`, `immich-offline-remover`) were observed `Up`/`(healthy)` via `docker ps --filter name=immich` at the time of this pass.

## Notes

- Uses a custom Postgres image with pgvector (`ghcr.io/immich-app/postgres`) — see the `homeserver-postgres` skill for why its `command:` override must keep `-c config_file=/etc/postgresql/postgresql.conf` as the first flag
- Major version bumps (e.g. v2 → v3) break compatibility with older mobile app builds — the server only supports the matching major client version. Update the mobile app(s) before or right after bumping the server's major version. Minor/patch bumps don't have this constraint.

## Troubleshooting: `immich-server` crash-loops with `Failed to read .../.immich: ENOENT`

**Symptom:** Immich does a create→read→overwrite self-check on a hidden `.immich` marker file in each `upload/` subdirectory on every boot (see [Immich's system-integrity docs](https://docs.immich.app/administration/system-integrity)). On Windows Docker Desktop, the read step can fail immediately after the write succeeds, even though the file is independently readable via a plain `docker run` — not a permissions or race issue, just how this host's bind mount behaves under Immich's own Node.js process.

**Fix:** `IMMICH_IGNORE_MOUNT_CHECK_ERRORS=true` in `services/immich/.env` (already set by default in this repo) — Immich's own documented escape hatch for this failure mode. It only skips the startup self-check; normal photo/video read/write during actual use is unaffected.

**Before assuming it's this bug, verify the mount is even correct:** `docker inspect immich-server --format '{{.Mounts}}'` and confirm the host path matches `UPLOAD_LOCATION` in `services/immich/.env`. `UPLOAD_LOCATION` is a separate env var from `DATA_ROOT` and does **not** get auto-injected by `homeserver.py` — if you ever restructure `service_data/` paths, grep every `.env`/`.env.example` for `=../../service_data/`, not just lines starting with `DATA_ROOT=`. A stale `UPLOAD_LOCATION` silently bind-mounts an empty auto-created directory, which looks identical to the mount-check bug above but is a different problem with a different fix (correct the path, not `IMMICH_IGNORE_MOUNT_CHECK_ERRORS`).

## Troubleshooting: `immich-server`/DB instability during heavy upload + processing

**Symptom:** Immich becomes unresponsive or connections get dropped/killed during large bulk uploads or heavy background job processing (thumbnail generation, face detection, smart search indexing all running at once).

**Root cause (confirmed 2026-07-12):** `immich-db`'s Postgres container was capped at only `512M` via `deploy.resources.limits.memory` — 4x below the **2GB Immich's own docs say Postgres needs** if a limit is set at all (docs.immich.app/install/requirements/). Bulk inserts and concurrent job-queue bookkeeping during heavy upload sessions push Postgres past that ceiling; the kernel OOM-killer then kills the container specifically (not a graceful shutdown), and `immich-server` — which depends on DB health — stalls/errors until it recovers. This reads as "Immich getting killed" from the outside.

**Fix applied:** raised `immich-db`'s memory limit to `2G` and scaled its tuning proportionally to actually use the extra headroom (not just raise the ceiling): `shared_buffers` 128MB→512MB, `effective_cache_size` 384MB→1536MB, `maintenance_work_mem` 64MB→256MB (faster VACUUM/index ops, relevant for a large photo library's DB). `work_mem` left at 4MB — fine at `max_connections=50`. Recreate just this container after changing these: `docker compose -f compose.yml -f compose.dev.yml up -d --no-deps immich-database` (or `compose.prod.yml`, matching whichever env is running).

**If this recurs even at 2GB:** check `docker inspect immich-db --format '{{.State.OOMKilled}}'` right after — `true` confirms the same failure mode, and the limit should be raised further rather than assumed fixed. No forensic OOM-kill logging exists in this stack by default (Windows/WSL2's kernel ring buffer rolls over, and container recreation resets `OOMKilled`/`RestartCount`), so catching it live via `docker stats` during an active upload is the reliable way to confirm before raising the cap again.

## Fixed: `UPLOAD_LOCATION` was nested inside `DATA_ROOT`, so every backup archived the whole photo/video library

**Symptom:** `uv run homeserver.py dev backup immich` (and any auto-snapshot on `down`) took a very long time and produced a huge `service_data.tar.gz`, dominated by the actual photo/video library rather than app config.

**Root cause:** `UPLOAD_LOCATION=../../service_data/data/immich/upload` was nested *inside* `DATA_ROOT` (`service_data/data/immich/`). `backup_service()` in `homeserver.py` tars the entire `DATA_ROOT` directory on every backup/auto-snapshot, so the whole `library/`/`thumbs/`/`encoded-video/`/`upload/` tree was being re-archived every time. Found via the identical bug on `jellyfin`'s `MEDIA_ROOT` — see `docs/services/jellyfin.md`.

**Fix:** moved the upload tree to `service_data/uploads/immich/` — a sibling of `service_data/data/`, structurally outside anything `backup_service()` sweeps — and updated `UPLOAD_LOCATION` accordingly. The container's mount target (at the time, `/usr/src/app/upload`) didn't change, only the host-side source path. Confirmed intact after the move: 28,683 files still present under `library/` from inside the container, `immich-server`/`immich-db` both came back healthy. This convention is now documented in the `homeserver-add-service` skill (step 2) for any service with a second, large secondary data root.

## Not a bug: `immich-server-data:/data` is an intentionally-unused decoy volume; real data lives under `/usr/src/app/upload`

**Why this looks wrong at first glance:** current upstream Immich (`docker/docker-compose.yml`, and `IMMICH_MEDIA_LOCATION`'s documented default — see [environment-variables docs](https://docs.immich.app/install/environment-variables)) mounts `UPLOAD_LOCATION` at `/data`. This stack instead mounts it at `/usr/src/app/upload` — an older, pre-1.137.0 Immich mount path — and separately declares an empty `immich-server-data:/data` named volume that nothing writes to. On the surface that looks like a leftover bug (empty volume, stale-looking path), but **do not "fix" it by just retargeting the mount to `/data`.**

**Why it's actually fine as-is:** Immich stores absolute file paths (thumbnails, encoded video, library entries) directly in its Postgres database, keyed to whatever the mount path was at write time. As long as the mount target never changes, everything stays internally consistent — which is exactly the case here; the host directory (`upload/`, `library/`, `thumbs/`, `encoded-video/`, `profile/`, `backups/`) has been reliably read/written at `/usr/src/app/upload` the whole time.

**Why blindly changing it is dangerous:** per Immich's own [Discussion #20488](https://github.com/immich-app/immich/discussions/20488), users who changed their mount from `/usr/src/app/upload` to `/data` without anything else got broken thumbnails/videos (`ENOENT` on the old path) because the *database* still had the old path prefix baked into every record. Immich only added auto-detection/correction of this exact mismatch in **v1.137.1**. Confirming that auto-fix is actually present and safe in the currently-pinned `v3.1.0` (a much later calendar-versioned release) was not verified before this was almost changed — treat any future mount-path change here as a real migration, not a one-line compose edit: verify the changelog, and check thumbnails/videos still load in the UI immediately after, before considering it done.

**The empty `immich-server-data` volume is harmless clutter, not a defect** — it's declared but never mounted to anything Immich reads/writes, so it costs nothing to leave in place. Removing it is a legitimate cleanup, but only as a mount-untouched change (drop the volume declaration and the `/data` mount line together, leave `/usr/src/app/upload` exactly as-is).

**Later consolidated into `service_data/media/immich/`** (a same-volume rename, so instant despite the ~145GB size) so the top-level `service_data/` layout is just `backup/`, `cache/`, `data/`, `media/` — one folder per concern, service-named subfolders inside each — rather than a one-off `uploads/` directory existing only for this service. `UPLOAD_LOCATION` updated to match; no other change needed since it's still a sibling of `service_data/data/immich/`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
