# Immich

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Photo management, replaces Google Photos.
**Port:** `2283` (host) → `2283` (container, `immich-server`) | **Requires:** Postgres (custom pgvector build) + Redis | **Memory:** DB capped 2G in compose.yml (raised from 512M — see incident below); app/ml/redis: no hard limit set; measured idle ~1.4GB total across all 5 containers. Immich's own docs state 6GB minimum / 8GB recommended for the full stack with ML enabled, and explicitly recommend **at least 2GB for Postgres** if a Docker memory limit is set on it at all

## Setup

```bash
cp immich/.env.example immich/.env
```

Edit `immich/.env`:

```env
UPLOAD_LOCATION=/mnt/seagate/immich
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

Login with the user's account, then enable auto-backup in app settings.

## Notes

- Uses a custom Postgres image with pgvector (`ghcr.io/immich-app/postgres`) — see the `homeserver-postgres` skill for why its `command:` override must keep `-c config_file=/etc/postgresql/postgresql.conf` as the first flag
- Major version bumps (e.g. v2 → v3) break compatibility with older mobile app builds — the server only supports the matching major client version. Update the mobile app(s) before or right after bumping the server's major version. Minor/patch bumps don't have this constraint.

## Troubleshooting: `immich-server` crash-loops with `Failed to read .../.immich: ENOENT`

**Symptom:** Immich does a create→read→overwrite self-check on a hidden `.immich` marker file in each `upload/` subdirectory on every boot (see [Immich's system-integrity docs](https://docs.immich.app/administration/system-integrity)). On Windows Docker Desktop, the read step can fail immediately after the write succeeds, even though the file is independently readable via a plain `docker run` — not a permissions or race issue, just how this host's bind mount behaves under Immich's own Node.js process.

**Fix:** `IMMICH_IGNORE_MOUNT_CHECK_ERRORS=true` in `immich/.env` (already set by default in this repo) — Immich's own documented escape hatch for this failure mode. It only skips the startup self-check; normal photo/video read/write during actual use is unaffected.

**Before assuming it's this bug, verify the mount is even correct:** `docker inspect immich-server --format '{{.Mounts}}'` and confirm the host path matches `UPLOAD_LOCATION` in `immich/.env`. `UPLOAD_LOCATION` is a separate env var from `DATA_ROOT` and does **not** get auto-injected by `homeserver.py` — if you ever restructure `service_data/` paths, grep every `.env`/`.env.example` for `=../service_data/`, not just lines starting with `DATA_ROOT=`. A stale `UPLOAD_LOCATION` silently bind-mounts an empty auto-created directory, which looks identical to the mount-check bug above but is a different problem with a different fix (correct the path, not `IMMICH_IGNORE_MOUNT_CHECK_ERRORS`).

## Troubleshooting: `immich-server`/DB instability during heavy upload + processing

**Symptom:** Immich becomes unresponsive or connections get dropped/killed during large bulk uploads or heavy background job processing (thumbnail generation, face detection, smart search indexing all running at once).

**Root cause (confirmed 2026-07-12):** `immich-db`'s Postgres container was capped at only `512M` via `deploy.resources.limits.memory` — 4x below the **2GB Immich's own docs say Postgres needs** if a limit is set at all (docs.immich.app/install/requirements/). Bulk inserts and concurrent job-queue bookkeeping during heavy upload sessions push Postgres past that ceiling; the kernel OOM-killer then kills the container specifically (not a graceful shutdown), and `immich-server` — which depends on DB health — stalls/errors until it recovers. This reads as "Immich getting killed" from the outside.

**Fix applied:** raised `immich-db`'s memory limit to `2G` and scaled its tuning proportionally to actually use the extra headroom (not just raise the ceiling): `shared_buffers` 128MB→512MB, `effective_cache_size` 384MB→1536MB, `maintenance_work_mem` 64MB→256MB (faster VACUUM/index ops, relevant for a large photo library's DB). `work_mem` left at 4MB — fine at `max_connections=50`. Recreate just this container after changing these: `docker compose -f compose.yml -f compose.dev.yml up -d --no-deps immich-database` (or `compose.prod.yml`, matching whichever env is running).

**If this recurs even at 2GB:** check `docker inspect immich-db --format '{{.State.OOMKilled}}'` right after — `true` confirms the same failure mode, and the limit should be raised further rather than assumed fixed. No forensic OOM-kill logging exists in this stack by default (Windows/WSL2's kernel ring buffer rolls over, and container recreation resets `OOMKilled`/`RestartCount`), so catching it live via `docker stats` during an active upload is the reliable way to confirm before raising the cap again.

## Fixed: `UPLOAD_LOCATION` was nested inside `DATA_ROOT`, so every backup archived the whole photo/video library

**Symptom:** `uv run homeserver.py dev backup immich` (and any auto-snapshot on `down`) took a very long time and produced a huge `service_data.tar.gz`, dominated by the actual photo/video library rather than app config.

**Root cause:** `UPLOAD_LOCATION=../service_data/data/immich/upload` was nested *inside* `DATA_ROOT` (`service_data/data/immich/`). `backup_service()` in `homeserver.py` tars the entire `DATA_ROOT` directory on every backup/auto-snapshot, so the whole `library/`/`thumbs/`/`encoded-video/`/`upload/` tree was being re-archived every time. Found via the identical bug on `jellyfin`'s `MEDIA_ROOT` — see `docs/services/jellyfin.md`.

**Fix:** moved the upload tree to `service_data/uploads/immich/` — a sibling of `service_data/data/`, structurally outside anything `backup_service()` sweeps — and updated `UPLOAD_LOCATION` accordingly. The container's mount target (`/usr/src/app/upload`) didn't change, only the host-side source path. Confirmed intact after the move: 28,683 files still present under `library/` from inside the container, `immich-server`/`immich-db` both came back healthy. This convention is now documented in the `homeserver-add-service` skill (step 2) for any service with a second, large secondary data root.

**Later consolidated into `service_data/media/immich/`** (a same-volume rename, so instant despite the ~145GB size) so the top-level `service_data/` layout is just `backup/`, `cache/`, `data/`, `media/` — one folder per concern, service-named subfolders inside each — rather than a one-off `uploads/` directory existing only for this service. `UPLOAD_LOCATION` updated to match; no other change needed since it's still a sibling of `service_data/data/immich/`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
