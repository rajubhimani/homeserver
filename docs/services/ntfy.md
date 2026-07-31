# ntfy

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted push notifications — scripts and services `curl` a message straight to your phone (via the ntfy app subscribed to a topic on this server).
**Port:** `8118` (host) → `80` (container) | **Data:** `service_data/data/ntfy/` | **Requires:** nothing (bundled SQLite for auth/cache)

## Setup

```bash
cp ntfy/.env.example ntfy/.env
uv run homeserver.py dev up ntfy
docker exec -it ntfy ntfy user add --role=admin youruser
```

Install the ntfy app (iOS/Android) or use the web UI at `https://ntfy.<domain>/`, point it at your server, and subscribe to a topic. Send a test message:

```bash
curl -u youruser -d "test message" https://ntfy.<domain>/mytopic
```

## Registration / access model

No public signup — `NTFY_AUTH_DEFAULT_ACCESS=deny-all` in `.env` means nobody can read or write any topic without an account created via `ntfy user add` (see Setup above). Set to `read-write` instead if you want it to behave like the open public `ntfy.sh` instance (no accounts, anyone can publish/subscribe to any topic name).

## Notes

- Auth database and message cache live under `service_data/data/ntfy/data/` (`auth.db`, `cache.db`).
- Health endpoint: `/v1/health`.
- `NTFY_BEHIND_PROXY=true` is required so ntfy trusts `X-Forwarded-For` from nginx-plain for correct rate-limiting/IP logging.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
