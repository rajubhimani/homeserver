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

Used by [ClamAV](clamav.md)'s watchdog (`clamav-watchdog`, `services/clamav/watchdog.sh`) to push a real notification when the signature database goes stale instead of that only being visible via `docker inspect`. An account (`rajubhimani`, admin role) and an access token scoped for this (`ntfy token add --label=clamav-watchdog rajubhimani`, stored as `NTFY_ALERT_TOKEN` in `services/clamav/.env`) already exist — this section is about **subscribing to actually receive** what gets published there, which only you can do (same category of thing as clicking through an OAuth consent screen — no way to do this on your behalf).

**To subscribe on your phone:** install the ntfy app (link above), tap **+**, server `https://ntfy.${DOMAIN}`, topic `homeserver-alerts`, log in with the `rajubhimani` account, **Subscribe**.

**To subscribe in a browser instead:** `https://ntfy.${DOMAIN}/homeserver-alerts` and log in the same way.

Any future watchdog in this stack can reuse the same topic (same pattern as `adguard-watchdog`, which currently just logs rather than alerting) rather than each needing its own — one subscription covers all of them.

## Notes

- Auth database and message cache live under `service_data/data/ntfy/data/` (`auth.db`, `cache.db`).
- Health endpoint: `/v1/health`.
- `NTFY_BEHIND_PROXY=true` is required so ntfy trusts `X-Forwarded-For` from nginx-plain for correct rate-limiting/IP logging.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
