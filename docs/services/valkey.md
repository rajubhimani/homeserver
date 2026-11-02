# Valkey (shared)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** One Redis-protocol server shared by your own projects and by any service that declares `shared_cache`, each with its own login limited to its own keys. Not a web app: no landing card, no public hostname.
**Port:** `6379` (host) → `6379` (container) | **Data:** named volume `valkey-data` (AOF) | **Tier:** extra | **Requires:** nothing

## Why this exists next to the per-app caches

Every existing app keeps its **own** Valkey (e.g. `outline-redis`) and is unchanged. This instance is the shared one: new or converted services, and your own projects, get a login on it instead of running another container. Nothing is migrated yet; a service opts in with `shared_cache` (below).

Valkey, not Redis: AWS ElastiCache and GCP Memorystore run Valkey, so it is the engine a move to a managed cache lands on (`docs/10-new-services.md`, "Managed-cloud parity"). Image `valkey/valkey:9.1.3-alpine`, the same pin as the other caches. Keep to the Redis 7.2 command set and database 0.

## Isolation: ACL login + key prefix (not like shared Postgres)

Postgres gives each app its own database and revokes everyone else's access to it. Valkey has no equivalent: ACLs can restrict keys and commands, but **not which database number (`SELECT n`) a login uses**. So each service's isolation is a **key prefix**:

- Its login can read and write only keys matching `<prefix>*` (and pub/sub channels `<prefix>*`). The prefix is the app's own key prefix, written exactly as the app applies it, and must end in `:`, `.`, `_` or `-` (for example `myapp:`), so it can't also match another app's keys.
- It cannot run `FLUSHALL`, `FLUSHDB`, `KEYS`, `CONFIG`, `ACL`, `DEBUG` and the rest of `@dangerous`/`@admin`. It can run `INFO` and `CLIENT SETNAME/SETINFO/ID`, which clients call when they connect.
- Everything lives in database 0, which keeps it compatible with managed clustered caches.

This only works for an app that can **prepend a key prefix** to everything it writes (a `keyPrefix`/namespace setting in its client or config). Most off-the-shelf apps cannot, and those stay on their own cache container.

## Giving a service a login (`shared_cache`)

1. In `services.json`, add to the service's entry. Values are key names in the app's own `.env`, or `=literal`:
   ```json
   "shared_cache": {"user": "CACHE_USER", "password": "CACHE_PASSWORD", "prefix": "CACHE_PREFIX"}
   ```
2. In the app's `.env` and `.env.example`: `CACHE_HOST=valkey`, `CACHE_PORT=6379`, `CACHE_USER`, `CACHE_PASSWORD`, `CACHE_PREFIX`. Remove the app's own cache container and point the app at these variables, with the prefix applied. Update its `docs/services/<app>.md` in the same pass.

`homeserver.py` then, on every `up`/`update`/`restart` of that service: starts `valkey` if it isn't running, and creates or refreshes the login (the password is reset to what the app's `.env` says, so editing `.env` rotates it), then runs `ACL SAVE` so logins survive a Valkey restart. User names and passwords may contain only letters, digits and `. _ ~ -`; `default` is reserved for the admin.

- Unlike shared Postgres, `valkey` is **never stopped automatically**: it is also an ordinary extra service you may be using by hand.
- `reset <service>` deletes that service's keys and login. Other services are untouched.
- If the app's `CACHE_HOST` is anything other than `valkey` (a managed cache, or its own container), `homeserver.py` leaves the shared server alone for it.
- Cache data is not part of per-app snapshots. It is a cache; the named volume `valkey-data` is not archived by `down`.

## Which services can use it

Checked on 2026-11-01 against each project's own source and docs. A service needs both a way to set a **key prefix** and a way to set a **username** (not just a password).

| Service | Prefix setting | Username | Verdict |
| --- | --- | --- | --- |
| Paperless | `PAPERLESS_REDIS_PREFIX`, documented for sharing one broker ("prefix for keys and channels") | `user:pass@` in the `PAPERLESS_REDIS` URL | **Candidate.** Not yet tested live. |
| Coolify | Laravel `REDIS_PREFIX` (default `coolify_database_`) | not confirmed | Possible. Check that Horizon and queue keys use the same prefix. |
| Penpot | a `tenant` setting goes into message-bus keys (dot-separated); not confirmed for all keys | `user:pass@` in the Redis URI | Unclear. Needs a check. |
| Outline | none (`REDIS_URL` only) | in the URL | No |
| Plane | none (`REDIS_URL` only) | in the URL | No |
| AppFlowy | none (URIs only) | in the URI | No |
| Ghostfolio | none (`REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`) | none (password only) | No |
| Zulip | none (the prefix setting exists for tests only) | none (password only) | No |
| ERPNext (Frappe) | keys are prefixed by site automatically, but queue keys are not, and it wants separate instances with different eviction policies | URL | No |
| Nextcloud, Immich | Nextcloud prefixes by instance ID itself; Immich has no setting | Nextcloud: yes | Not eligible: CORE services keep their own cache, as they keep their own database |

"No" means the service stays on its own cache container. Without a prefix, a login can't be limited to its own keys, and a login with access to everything isolates nothing.

## Setup

```bash
cp services/valkey/.env.example services/valkey/.env   # then set VALKEY_PASSWORD (openssl rand -hex 24)
chmod 600 services/valkey/.env
uv run homeserver.py dev up valkey
```

## Connecting

| From | Address |
| --- | --- |
| Another container on the `homeserver` network | `valkey:6379` |
| This machine | `localhost:6379` |
| Over WireGuard (prod) | `10.8.0.1:6379` |

Every connection must authenticate. Apps take the endpoint and login from their own `.env`, never hardcoded (`CACHE_HOST`, `CACHE_PORT`, `CACHE_USER`, `CACHE_PASSWORD`, `CACHE_PREFIX`). For your own projects, use the admin password (`VALKEY_PASSWORD`, user `default`) only on your machine; give anything that runs as a service its own login.

Quick test as the admin:

```bash
docker exec -it valkey sh -c 'REDISCLI_AUTH="$VALKEY_PASSWORD" valkey-cli ping'
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `VALKEY_PASSWORD` | `change_me` | Admin ("default") password. Rewritten into the ACL file on every start. |
| `VALKEY_MAXMEMORY` | `256mb` | RAM ceiling |
| `VALKEY_MAXMEMORY_POLICY` | `allkeys-lru` | Eviction at the ceiling. `allkeys-lru` = cache behaviour; `noeviction` = writes fail instead of dropping keys. |

AOF persistence is on (`--appendonly yes`), so keys survive restarts. Logins are stored in `/data/users.acl` on the same volume.

## Notes

- Dev publishes on all interfaces; prod on `127.0.0.1` and the WireGuard address only. The port is never opened on the router and does not go through the Cloudflare tunnel (it is not HTTP).
- Data lives in a named volume, so it is outside `service_data/data/` and the `down` auto-snapshot does not archive it.
