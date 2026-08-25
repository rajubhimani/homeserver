# Vaultwarden

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted password manager (Bitwarden-compatible).
**Port:** `8200` (host) → `80` (container) | **Data:** `service_data/data/vaultwarden/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~14MB

## Setup

```bash
cp services/vaultwarden/.env.example services/vaultwarden/.env
# set ADMIN_TOKEN (openssl rand -base64 48)
uv run homeserver.py dev up vaultwarden
```

**First login:** `SIGNUPS_ALLOWED` defaults to `false` (closed) — set it to `true` first, `up`/restart, browse to `https://vaultwarden.${DOMAIN}` (or `http://<ip>:8200` in dev) and register your first account directly on that page, then set it back to `false` and restart. See Registration below for adding more accounts afterward without reopening public signup.

## Health endpoint

Confirmed live against the running container (`vaultwarden/server:1.37.2`): the image ships its own `/healthcheck.sh` baked into `CMD` (60s interval, 10s timeout) — this repo's `compose.yml`/`compose.dev.yml` do not define a separate `healthcheck:` block, `docker inspect` shows the image default is in effect. The script curls `http://localhost:80/alive` (reading `ROCKET_PORT`/`DOMAIN` from the container's own env/`config.json` to build the URL) and exits non-zero on anything but success.

`GET /alive` returns HTTP `200` with a bare JSON timestamp string, e.g. `"2026-08-21T22:37:44.046902Z"` — confirmed both with `docker exec vaultwarden curl http://localhost:80/alive` and with `curl http://localhost:8200/alive` from the host (dev port). `docker ps` / `docker inspect` reports the container as `healthy` accordingly.

## Admin panel

`http://<ip>:8200/admin` → enter `ADMIN_TOKEN`.

## Registration

`.env.example` ships with `SIGNUPS_ALLOWED=false` (closed) — add every account after the first via the admin panel → Users → Invite instead (see Admin panel above for the `ADMIN_TOKEN` login). Set it back to `true` only if open self-signup is actually wanted.

## Making devices actually use it

Vaultwarden implements the real Bitwarden server API, so every **official Bitwarden client** — not a Vaultwarden-specific app — works against it unmodified, once pointed at this server instead of bitwarden.com. Confirmed against Bitwarden's own current Help Center (`bitwarden.com/help/change-client-environment`), not assumed from memory — the exact dropdown label differs by client, which a previous pass over this doc got wrong (see below).

- **Browser extension (Chrome, Firefox, Edge, Safari, Brave, etc.):** install "Bitwarden Password Manager" from that browser's extension store. On the login screen, click **Logging in on** → select **Self-hosted** from the dropdown, then enter the server URL *with* the scheme — `https://vaultwarden.${DOMAIN}` (a bare hostname or `http://` is rejected) — and **Save**. Then log in with the account created above.
- **Mobile app (Android/iOS):** install "Bitwarden Password Manager" — Android via Google Play, iOS via the App Store. Same self-hosted flow as the extension: on the login screen tap **Logging in on** → **Self-hosted**, enter `https://vaultwarden.${DOMAIN}`, then log in. Not independently installed/tested live as part of this pass (no test device available) — flow taken directly from Bitwarden's current Help Center, not assumed from memory.
- **Desktop app (Windows/macOS/Linux) — different dropdown label, corrected here:** the desktop app's equivalent control is labeled **Accessing**, not **Logging in on** (a previous pass over this doc incorrectly claimed it was "the identical field"). On the login screen, select **Accessing** → **Self-hosted**, enter `https://vaultwarden.${DOMAIN}`, and **Save**. Also not independently installed/tested live — taken from Bitwarden's Help Center.
- **Managed/enterprise deployments only:** the self-hosted URL can be pre-configured via browser policy instead of typing it in by hand (extension ID `nngceckbapebfimnlniiiahkandclblb`, policy key `base` set to the server URL) — not needed for a normal single-user setup, only worth knowing if ever deploying this to multiple managed devices at once.

### Client version compatibility with this stack's pinned Vaultwarden version

This stack pins `vaultwarden/server:1.37.2`. Checked directly against Vaultwarden's own GitHub release notes (not assumed): 1.37.0 first required newer Bitwarden clients (2026.7.0+, an updated `/identity/accounts/prelogin` flow, updated registration requests, and a `vnext` policy format); 1.37.2 is a maintenance release on top (Debian build fix, sendmail permission-check fix, login logs now include the user's email) that states it's *"required for support with clients with version 2026.8.0+"*. Running 1.37.2 means current Bitwarden clients are expected to work correctly against this instance — if a client ever reports a login/registration failure after an autoupdate, the Vaultwarden image pin here (not the client) is the first thing to check.

## Using it day to day

Confirmed against Bitwarden's own current Help Center, not assumed from memory.

- **Organizations (sharing with others):** in the web vault, **New organization** creates a shared space with its own **Admin Console** for managing members and items. Free/self-hosted plans cover the basics needed here — invite members from the Admin Console's Members page, then move or share vault items into the organization so members other than you can see them.
- **Collections:** shared-folder equivalents inside an organization — create one under the org's Collections page, then assign members/groups to it with their own permission level (view vs. edit). An item can belong to several collections; a member only sees the collections they've been granted access to, so collections are the actual sharing/access-control unit, not the organization membership alone.
- **Admin panel vs. vault login — these are separate accounts/purposes.** The `/admin` panel (gated by `ADMIN_TOKEN`, see above) is instance-level administration: user list, diagnostics, disabling accounts, server config overrides. It has no vault of its own and isn't where you store or view passwords — that's the normal login at `https://vaultwarden.${DOMAIN}` with a real user account, same as any Bitwarden client.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
