# Conduit (Matrix)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Lightweight Matrix homeserver for self-hosted chat.
**Port:** `8095` (client), `8448` (federation) → `6167` (container) | **Data:** `service_data/data/conduit/data/`

## Setup

```bash
cp conduit/.env.example conduit/.env
uv run homeserver.py dev up conduit
```

## Creating the first accounts

Temporarily set `ALLOW_REGISTRATION=true` in `conduit/.env`, restart, register accounts, then set it back to `false`.

Connect with any Matrix client (Element, FluffyChat) to `https://conduit.yourdomain.com`.

## Notes

- Distroless image — **no shell available inside the container**, and it emits no startup logs, so failures are silent
- Configure via `conduit/conduit.toml`

## Troubleshooting: process running but not listening on port 6167

**Symptom:** `docker top conduit` shows the process running, but `ss -tlnp` shows nothing listening on port 6167, and HTTP connections are refused or reset.

**Cause:** most common cause is a first-start race or a stale RocksDB lock left over from a previous run. Because the image is distroless, there's no log output to confirm this directly.

**Fix** — restart the container:

```bash
docker restart conduit
```

Verify it's up:

```bash
curl -s http://127.0.0.1:8095/_matrix/client/versions
```

If still failing, check for a stale lock file:

```bash
ls service_data/data/conduit/data/LOCK
# If present and conduit is not running, delete it:
rm service_data/data/conduit/data/LOCK
docker restart conduit
```

## Troubleshooting: landing page shows "offline" even though conduit is healthy and logging normally

Two things to check, and both are already correctly configured in this repo's `conduit.toml`/`landing/nginx.conf` — this section explains why, so you don't accidentally undo either one:

1. **`conduit.toml` must set `address = "0.0.0.0"`.** Conduit (like many Rust servers) defaults to binding `127.0.0.1` only when `address` isn't set explicitly — meaning it would never accept connections from *other containers* on the `homeserver` network, only from inside its own container/network namespace. Symptom if this regresses: `wget`/`curl` from another container to `http://conduit:6167/...` gets `Connection refused`, while the container itself looks perfectly healthy in its own logs (Conduit's distroless image has no shell/HTTP tools for a real healthcheck, so nothing internal would catch this).
2. **The `/health/conduit` block in `landing/nginx.conf` must proxy to `/_matrix/client/versions`, not `/health`** — Matrix homeservers don't expose a generic `/health` route, so `/health` 404s, which the landing page's poller reads as offline. `/_matrix/client/versions` returns `200` with a JSON version list for any working homeserver — the same technique any Matrix monitoring tool uses.

If you change either file, restart the affected service to pick it up — both are bind-mounted so `docker restart <service>` (or `uv run homeserver.py dev restart <service>`) is enough, no rebuild needed.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
