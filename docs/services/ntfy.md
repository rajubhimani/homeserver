# ntfy

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted push notifications — scripts and services `curl` a message straight to your phone (via the ntfy app subscribed to a topic on this server).
**Port:** `8118` (host) → `80` (container) | **Data:** `service_data/data/ntfy/` | **Requires:** nothing (bundled SQLite for auth/cache)

## Setup

```bash
cp services/ntfy/.env.example services/ntfy/.env
uv run homeserver.py dev up ntfy
docker exec -it ntfy ntfy user add --role=admin youruser
```

Install the official **ntfy** Android app ([Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy) or F-Droid) — tap **+** → enter the server `https://ntfy.<domain>` and a topic name (any string, acts like a password if kept private) → **Subscribe**. Or use the web UI at `https://ntfy.<domain>/` the same way, no app needed. Send a test message:

```bash
curl -u youruser -d "test message" https://ntfy.<domain>/mytopic
```

## Registration / access model

Public self-signup is enabled (`NTFY_ENABLE_SIGNUP=true`) via the web UI, but `NTFY_AUTH_DEFAULT_ACCESS=deny-all` in `.env` means a freshly signed-up account still can't read or write any topic until an admin grants access with `docker exec -it ntfy ntfy access <user> <topic> <permission>`. Set `NTFY_AUTH_DEFAULT_ACCESS=read-write` instead if you want it to behave like the open public `ntfy.sh` instance (no accounts, anyone can publish/subscribe to any topic name). Set `NTFY_ENABLE_SIGNUP=false` to go back to admin-only account creation via `ntfy user add` (see Setup above).

## Notes

- Auth database and message cache live under `service_data/data/ntfy/data/` (`auth.db`, `cache.db`).
- Health endpoint: `/v1/health`.
- `NTFY_BEHIND_PROXY=true` is required so ntfy trusts `X-Forwarded-For` from nginx-plain for correct rate-limiting/IP logging.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
