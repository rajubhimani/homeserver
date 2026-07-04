# Conduit (Matrix)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Lightweight Matrix homeserver for self-hosted chat.
**Port:** `8095` (client), `8448` (federation) → `6167` (container) | **Data:** `service_data/conduit/`

## Setup

```bash
cp conduit/.env.example conduit/.env
sh homeserver.sh dev up conduit
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
ls service_data/conduit/data/LOCK
# If present and conduit is not running, delete it:
rm service_data/conduit/data/LOCK
docker restart conduit
```

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
