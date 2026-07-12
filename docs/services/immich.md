# Immich

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Photo management, replaces Google Photos.
**Port:** `2283` (host) → `2283` (container, `immich-server`)

## Setup

```bash
cp immich/.env.example immich/.env
uv run homeserver.py dev up immich
```

## First login

Admin account is created on first browser visit — no env var needed.

## Notes

- Mobile app: connect to `https://immich.yourdomain.com` or `https://photos.yourdomain.com`
- ML (face recognition) is opt-in: `uv run homeserver.py dev up immich --profile ml`
- Uses a custom Postgres image with pgvector (`ghcr.io/immich-app/postgres`) — see the `homeserver-postgres` skill for why its `command:` override must keep `-c config_file=/etc/postgresql/postgresql.conf` as the first flag
- Major version bumps (e.g. v2 → v3) break compatibility with older mobile app builds — the server only supports the matching major client version. Update the mobile app(s) before or right after bumping the server's major version. Minor/patch bumps don't have this constraint.

## Troubleshooting: `immich-server` crash-loops with `Failed to read .../.immich: ENOENT`

**Symptom:** Immich does a create→read→overwrite self-check on a hidden `.immich` marker file in each `upload/` subdirectory on every boot (see [Immich's system-integrity docs](https://docs.immich.app/administration/system-integrity)). On Windows Docker Desktop, the read step can fail immediately after the write succeeds, even though the file is independently readable via a plain `docker run` — not a permissions or race issue, just how this host's bind mount behaves under Immich's own Node.js process.

**Fix:** `IMMICH_IGNORE_MOUNT_CHECK_ERRORS=true` in `immich/.env` (already set by default in this repo) — Immich's own documented escape hatch for this failure mode. It only skips the startup self-check; normal photo/video read/write during actual use is unaffected.

**Before assuming it's this bug, verify the mount is even correct:** `docker inspect immich-server --format '{{.Mounts}}'` and confirm the host path matches `UPLOAD_LOCATION` in `immich/.env`. `UPLOAD_LOCATION` is a separate env var from `DATA_ROOT` and does **not** get auto-injected by `homeserver.py` — if you ever restructure `service_data/` paths, grep every `.env`/`.env.example` for `=../service_data/`, not just lines starting with `DATA_ROOT=`. A stale `UPLOAD_LOCATION` silently bind-mounts an empty auto-created directory, which looks identical to the mount-check bug above but is a different problem with a different fix (correct the path, not `IMMICH_IGNORE_MOUNT_CHECK_ERRORS`).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
