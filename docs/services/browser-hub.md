# Browser Hub

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** One public entry point, one shared login, five real browsers (Firefox, Chromium, Ungoogled Chromium, Brave, Mullvad Browser) running on the server and controlled remotely — for reaching sites blocked on your own device or local network.
**Port:** n/a — subpath-routed through `nginx-plain`, not a container of its own | **Login:** `BROWSER_HUB_USER`/`BROWSER_HUB_PASSWORD` in the repo **root** `.env` (like `DOMAIN`) | **Requires:** the five browser containers (see their own docs) | **Memory:** no hard limit set on any browser container; measured idle varies notably by browser (see individual docs) — roughly 207-442MB each, ~1.64GB total if all five are running at once

---

## What it is

Five separate remote-browser containers ([firefox](firefox.md), [chromium](chromium.md), [ungoogled-chromium](ungoogled-chromium.md), [brave](brave.md), [mullvad-browser](mullvad-browser.md)) that deliberately do **not** get their own public subdomain. Instead, `nginx-plain` exposes exactly one hostname — `browser.${DOMAIN}` — gated by one shared HTTP Basic Auth login, serving a small static page listing all five. Picking one proxies you into that container at a subpath (`/firefox/`, `/chromium/`, etc.). There is no route to any of the five containers except through this one gated hostname — hitting an old-style `firefox.${DOMAIN}` returns a hard-closed connection (444) from nginx-plain's catch-all block, not even a login prompt, since no such route exists.

| Browser | Subpath | Doc |
| --- | --- | --- |
| Firefox | `/firefox/` | [firefox.md](firefox.md) |
| Chromium | `/chromium/` | [chromium.md](chromium.md) |
| Ungoogled Chromium | `/ungoogled-chromium/` | [ungoogled-chromium.md](ungoogled-chromium.md) |
| Brave | `/brave/` | [brave.md](brave.md) |
| Mullvad Browser | `/mullvad-browser/` | [mullvad-browser.md](mullvad-browser.md) |

## Why subpaths instead of one-login-per-app

Every other service in this stack gets `service.${DOMAIN}` with its own login. Doing that here would mean five separate credential prompts to remember and re-enter. Centralizing at one nginx server block also happens to make this design easy to upgrade later — see "Swapping to SSO" below.

## Access

`https://browser.${DOMAIN}/` → static hub page → click a browser → proxied to that container at its subpath. The individual browsers' own `CUSTOM_USER`/`PASSWORD` logins stay active underneath as defense-in-depth (see each browser's own doc) — in normal use over `browser.${DOMAIN}` you get exactly one prompt, not two, because both layers are wired to the exact same credential; see "Two login layers, one source of truth" below.

## Setup

```bash
# Edit the REPO ROOT .env (not any per-service .env) — set your own values:
#   BROWSER_HUB_USER=<username>
#   BROWSER_HUB_PASSWORD=<password>

uv run homeserver.py dev up browser
```

`browser` here is a **bundle**, not a real service directory — `up browser` (bare, not `group:browser`) expands to all five browser containers plus `nginx-plain` (needed for the hub's routing to work, brought up automatically if it isn't already running). `down browser`/`restart browser`/etc. only ever touch the five browsers themselves, never `nginx-plain` — it's shared infra for the whole stack, not something this bundle owns. See the `homeserver-add-service` skill's bundle-schema step for how this is wired (`"bundle"`/`"virtual"`/`"requires"` fields in `services.json`) if you're ever adding a similar multi-container hub.

**Change the credentials the same way any time** — edit those two root-`.env` values, then re-run the `up` command above (or `restart` the same six services). Nothing else to touch. `homeserver.py`'s `compose_env()` injects `BROWSER_HUB_USER`/`BROWSER_HUB_PASSWORD` into every service's `docker compose` invocation the same way it already does `DOMAIN` — so both `nginx-plain`'s auth gate and every browser's own `CUSTOM_USER`/`PASSWORD` always resolve to the exact same value, straight from one place, with nothing per-service left to fall out of sync. `nginx-plain`'s `docker-entrypoint.d/25-generate-browser-htpasswd.sh` hashes it (SHA-512 crypt, via BusyBox's `mkpasswd` already in the `nginx:alpine` image — no extra tooling) and writes `/etc/nginx/browser_htpasswd` fresh on every start; nothing else to hand-generate. Root `.env` ships with the placeholder `admin` / `changeme` — **change it** before relying on this for anything real, this container is public-facing.

**This wasn't the first design** — an earlier version kept `BROWSER_HUB_USER`/`PASSWORD` in `services/nginx-plain/.env` only, with each browser keeping its own separate `<SERVICE>_USER`/`PASSWORD` (`FIREFOX_USER`, `CHROMIUM_USER`, etc.). Changing the hub password without also updating all five browsers' own copies broke logins — nginx's gate would accept the new password, then proxy through to a browser container still checking against the old one, producing a second prompt that could never succeed. The root-`.env`-injection design above exists specifically because that happened.

## Two login layers, one source of truth

1. **`nginx-plain`'s shared Basic Auth** on the whole `browser.${DOMAIN}` server block — gates every path under that host, not just `/`.
2. **Each container's own `CUSTOM_USER`/`PASSWORD`** — kept as defense-in-depth in case a container is ever reached directly (its dev port, e.g. `8145` for Firefox, bypasses `nginx-plain` entirely — see [11-services-reference.md](../11-services-reference.md)'s Port Reference table).

Both layers read `${BROWSER_HUB_USER}`/`${BROWSER_HUB_PASSWORD}` — there's no separate credential to keep in sync by hand. Since nginx also forwards the `Authorization` header through to the upstream by default (nothing strips it), the browser's cached credentials from the hub's initial challenge get auto-resent and satisfy each container's own check too — one prompt in practice, not five.

## SUBFOLDER — the part that needed verifying

Each browser's `compose.yml` sets `SUBFOLDER=/firefox/` (etc.) — a `linuxserver/docker-baseimage-selkies` env var telling the app it's being served from a subpath rather than domain root, so its own generated asset/API/WebSocket URLs are subpath-aware. Upstream's docs only specify the format (`/subfolder/`, both slashes required) with no worked reverse-proxy example, so nginx-plain's location blocks were built on the standard "subpath-aware app" idiom: `proxy_pass http://firefox:3000;` with **no URI component** after the host, so the full incoming path (including `/firefox/...`) is forwarded unchanged rather than stripped — matching what a `SUBFOLDER`-aware app expects to receive.

**Verify this actually works after any Selkies base-image update**: load `https://browser.${DOMAIN}/firefox/`, confirm the desktop/browser UI renders (not a blank page or broken asset icons), and confirm the remote session actually responds to clicks (proves the WebSocket stream survived the subpath proxy, not just the initial HTML).

**Related gotcha, already fixed once**: every `proxy_pass` referencing a member container by hostname in `default.conf.template` — including the `/_status/<slug>` liveness-check locations the hub page's own JS polls — must use the `set $upstream http://firefox:3000; proxy_pass $upstream;` indirection, never a literal `proxy_pass http://firefox:3000;`. The literal form makes nginx resolve that hostname at config-load time, which fails hard (`nginx: [emerg] host not found in upstream`) if `nginx-plain` starts before that container exists on the network — a real race on a fresh `up browser`, not hypothetical (it happened: the `/_status/*` locations were written with the literal form and intermittently crashed `nginx-plain` on cold start until fixed).

## Swapping to SSO later (Authentik or Authelia)

This design is SSO-migration-friendly by construction: auth is centralized at **one** nginx server block instead of scattered across five. Upgrading later means:

1. Stand up Authentik or Authelia as its own service
2. Configure one forward-auth application/provider for `browser.${DOMAIN}`
3. In `services/nginx-plain/templates/default.conf.template`, replace this block's `auth_basic`/`auth_basic_user_file` lines with the forward-auth tool's standard `auth_request` block (a few lines, from that tool's own docs)

The five browser containers, their `SUBFOLDER` routing, and the static hub page don't need to change at all.

**Authelia** was evaluated and deferred (2026-08-19) in favor of keeping Basic Auth for now — it would give a real HTML login form (better Vaultwarden autofill, works from mobile app too, not just the browser extension) at the cost of a new service (~1GB RAM headroom for its argon2id password hashing, file-based users). **Authentik** was ruled out earlier for the same reason at higher cost (~745MB idle, full multi-container Postgres-backed stack, per-app admin-UI configuration) — see [authentik.md](authentik.md).

## Landing page presence

All six cards (the hub itself plus its five members) live under System → **Browsers**, a subcategory dedicated to this bundle (`services.json`'s `subcategoryLabels.browsers`). Each of the five browsers has its own real card with its own live status dot, driven by the normal per-card `/health/<slug>` mechanism every other card uses (see `services/landing/nginx.conf`) — nothing custom, so a future bundle member gets working status for free just by getting a card the normal way. Each member's public link points at its subpath under the *hub's* subdomain (`https://browser.${DOMAIN}/firefox/`, not `https://${DOMAIN}/browser/firefox` — that URL never existed and 404s, a bug caught and fixed once already) — set via `"sub": "browser"` + `"path": "firefox/"` (trailing slash required — nginx's `location /firefox/ { ... }` is a prefix match) on each member's `services.json` entry, which `buildCard()` combines as `https://${sub}.${DOMAIN}/${path}` before falling back to the default `https://${sub}.${DOMAIN}`. The hub's own card needs neither field — its slug already equals its subdomain.

The hub's own card (`services.json` slug `browser`) is marked `"virtual": true` — it has a landing-page presence but no `services/browser/compose.yml`; `homeserver.py` excludes `virtual` entries from `SERVICES_MIN`/`CORE`/`EXTRA`/`MANUAL` and from automatic category/subcategory `SERVICE_GROUPS` derivation, so `up all`/`up group:browsers`/etc. never try to docker-compose a directory that doesn't exist.

## Gotchas

- **`RESTART_APP=true` is set on every browser** — compensates for `HARDEN_DESKTOP` above disabling the terminal and xdg-open. Without it, accidentally closing the browser *application itself* inside the remote desktop (not just your own viewing tab — that's harmless, see "Access" above) would strand the session with no in-desktop way to relaunch it, short of restarting the whole container. This watchdog auto-relaunches the main app whenever it exits.
- **Dev-port direct access bypasses the hub entirely.** Each browser's `compose.dev.yml` still exposes its own host port (Firefox `8145`, Chromium `8146`, etc.) for local debugging convenience — that path only has the container's own `CUSTOM_USER`/`PASSWORD` gate, not the hub's shared login. This is consistent with how every other service in this stack treats `dev` ports (LAN-trusted convenience), not a gap specific to this design.
- **One shared user only, by design** — `25-generate-browser-htpasswd.sh` overwrites `/etc/nginx/browser_htpasswd` with exactly one `BROWSER_HUB_USER`/`PASSWORD` line on every container start, trading away multi-user support for a single `.env` value that's easy to find and hard to get wrong. If separate per-person logins are ever wanted, that script would need to loop over a list of users instead — not built, since this stack's auth-posture convention already treats this as Bucket B (shared credential, see [13-auth-posture.md](../13-auth-posture.md)), same as several other services here.
- If you add a sixth browser later, it needs: its own `compose.yml`/`.env` (with `SUBFOLDER=/<slug>/`), a new `location /<slug>/ { ... }` block copied from an existing one in `default.conf.template`, and a new link on `services/nginx-plain/html/browser-hub/index.html` — the hub page is static, not generated from `services.json`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
