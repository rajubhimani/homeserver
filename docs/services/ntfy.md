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

`NTFY_ENABLE_SIGNUP` defaults to `false` (closed) — accounts are admin-only, created with `docker exec -it ntfy ntfy user add <username>` (add `--role=admin` for an admin account; see Setup above). Combined with `NTFY_AUTH_DEFAULT_ACCESS=deny-all` in `.env`, nobody can read or write any topic without an account an admin explicitly created and granted access to via `docker exec -it ntfy ntfy access <user> <topic> <permission>`. Set `NTFY_ENABLE_SIGNUP=true` instead if you want public self-signup back (accounts still start with no topic access under `deny-all`), or `NTFY_AUTH_DEFAULT_ACCESS=read-write` if you want it to behave like the open public `ntfy.sh` instance (no accounts, anyone can publish/subscribe to any topic name).

## `homeserver-alerts` topic — watchdog notifications

Used by the stack's own monitors to push real notifications: [Uptime Kuma](uptime-kuma.md)'s ntfy channel (any container down or unhealthy, including ClamAV's stale-signature check), `adguard-watchdog` (each network repair) and the host's data-drive watch (`docker/host-boot-safety.sh`). An admin account (`admin`) and an access token for this (labeled `homeserver-alerts`) already exist. The publish URL and token are `NTFY_ALERT_URL`/`NTFY_ALERT_TOKEN` in `services/ntfy/.env`, the canonical copy; `services/adguard-home/.env` holds the same values for its watchdog. this section is about **subscribing to actually receive** what gets published there, which only you can do (same category of thing as clicking through an OAuth consent screen — no way to do this on your behalf).

**To subscribe on your phone:** install the ntfy app (link above), tap **+**, server `https://ntfy.${DOMAIN}`, topic `homeserver-alerts`, log in with the `admin` account, **Subscribe**.

**Only one admin account exists** (`admin`) — an earlier `rajubhimani` account was created and then deliberately removed to avoid two overlapping full-access accounts on a single-person instance. If you ever add a real second person, create a dedicated non-admin account for them (`ntfy user add <name>`) rather than sharing `admin`, and grant only the specific topics they need via `ntfy access <name> <topic> <permission>`.

**To subscribe in a browser instead:** `https://ntfy.${DOMAIN}/homeserver-alerts` and log in the same way.

Any future watchdog in this stack can reuse the same topic (same pattern as `adguard-watchdog`, which currently just logs rather than alerting) rather than each needing its own — one subscription covers all of them.

## Notes

- Auth database and message cache live under `service_data/data/ntfy/data/` (`auth.db`, `cache.db`).
- Health endpoint: `/v1/health`.
- `NTFY_BEHIND_PROXY=true` is required so ntfy trusts `X-Forwarded-For` from nginx-plain for correct rate-limiting/IP logging.
- **Reverse proxy needs WebSocket upgrade headers and buffering disabled, or push is not instant.** Subscribers (the phone app, the web UI) hold a long-lived connection open — either a real WebSocket (`/<topic>/ws`) or a chunked JSON stream (`/<topic>/json`) — with a keepalive ping every ~30s, and only pick up new messages the moment they arrive on that connection. `nginx-plain`'s `ntfy.${DOMAIN}` block was missing `proxy_set_header Upgrade`/`Connection $connection_upgrade` (breaking the WebSocket handshake outright — confirmed live, `curl` got a hung connection instead of `101 Switching Protocols` before the fix) and `proxy_buffering off` (without it, nginx holds the streamed response in its own buffer instead of flushing it to the client immediately, so messages only show up once the app happens to reconnect — e.g. on a manual pull-to-refresh). Both fixed in the same block as the rest of nginx-plain's websocket-upgrade services; verified after the fix with a real WebSocket handshake over the public domain (`101 Switching Protocols`) and a published message arriving on an open stream within ~1s.


## Fresh-install verification (2026-10-03)

Reset to an empty install, came up healthy, then restored from its `reset-backup-*` snapshot and came up healthy again: users, tokens and topics restored. Procedure: [16 — MIN/CORE reset runbook](../16-min-core-reset-runbook.md).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
