# Browser Hub

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** One public entry point, one SSO login, five real browsers (Firefox, Chromium, Ungoogled Chromium, Brave, Mullvad Browser) running on the server and controlled remotely — for reaching sites blocked on your own device or local network.
**Port:** n/a — subpath-routed through `nginx-plain`, not a container of its own | **Login:** Authentik forward-auth on `browser.${DOMAIN}` (see [authentik.md](authentik.md)) — same SSO session as every other forward-auth-gated service in this stack | **Requires:** the five browser containers (see their own docs) | **Memory:** no hard limit set on any browser container; measured idle varies notably by browser (see individual docs) — roughly 207-442MB each, ~1.64GB total if all five are running at once

---

## What it is

Five separate remote-browser containers ([firefox](firefox.md), [chromium](chromium.md), [ungoogled-chromium](ungoogled-chromium.md), [brave](brave.md), [mullvad-browser](mullvad-browser.md)) that deliberately do **not** get their own public subdomain. Instead, `nginx-plain` exposes exactly one hostname — `browser.${DOMAIN}` — gated by Authentik forward-auth, serving a small static page listing all five. Picking one proxies you into that container at a subpath (`/firefox/`, `/chromium/`, etc.). There is no route to any of the five containers except through this one gated hostname — hitting an old-style `firefox.${DOMAIN}` returns a hard-closed connection (444) from nginx-plain's catch-all block, not even a login prompt, since no such route exists.

| Browser | Subpath | Doc |
| --- | --- | --- |
| Firefox | `/firefox/` | [firefox.md](firefox.md) |
| Chromium | `/chromium/` | [chromium.md](chromium.md) |
| Ungoogled Chromium | `/ungoogled-chromium/` | [ungoogled-chromium.md](ungoogled-chromium.md) |
| Brave | `/brave/` | [brave.md](brave.md) |
| Mullvad Browser | `/mullvad-browser/` | [mullvad-browser.md](mullvad-browser.md) |

## Why subpaths instead of one-login-per-app

Every other service in this stack gets `service.${DOMAIN}` with its own login. Doing that here would mean five separate credential prompts to remember and re-enter. Centralizing at one nginx server block also happens to make this design easy to upgrade later — see "SSO at the hub level" below (that upgrade already happened).

## Access

`https://browser.${DOMAIN}/` → Authentik login (shared SSO session with every other forward-auth-gated service in this stack — see [authentik.md](authentik.md)) → static hub page → click a browser → proxied to that container at its subpath. That's the **only** login layer now — the individual browsers' own `CUSTOM_USER`/`PASSWORD` Basic Auth was removed entirely (see "Auth history" below), so one Authentik login covers the hub page and every browser subpath, no second prompt.

## Setup

```bash
uv run homeserver.py dev up browser
```

`browser` here is a **bundle**, not a real service directory — `up browser` (bare, not `group:browser`) expands to all five browser containers plus `nginx-plain` (needed for the hub's routing to work, brought up automatically if it isn't already running). `down browser`/`restart browser`/etc. only ever touch the five browsers themselves, never `nginx-plain` — it's shared infra for the whole stack, not something this bundle owns. See the `homeserver-add-service` skill's bundle-schema step for how this is wired (`"bundle"`/`"virtual"`/`"requires"` fields in `services.json`) if you're ever adding a similar multi-container hub.

There's no browser-hub-specific credential to set up anymore — access is controlled entirely through Authentik (create/manage users there, see [authentik.md](authentik.md)). Nothing in any browser's `.env` or `nginx-plain`'s `.env` needs editing for auth.

## Auth history

This design went through three shapes, each retiring the one before it:

1. **Per-browser credentials** (`FIREFOX_USER`/`PASSWORD`, `CHROMIUM_USER`/`PASSWORD`, etc., set independently per service). Changing one browser's password without updating nginx's own gate to match broke logins — a real incident that motivated the next design.
2. **One shared Basic Auth credential** (`BROWSER_HUB_USER`/`BROWSER_HUB_PASSWORD` in the repo root `.env`, injected by `homeserver.py` into both `nginx-plain`'s `auth_basic` gate and every browser container's own `CUSTOM_USER`/`PASSWORD`) — one credential, one place to change it, and nginx forwarding the `Authorization` header through meant one prompt satisfied both layers.
3. **Authentik forward-auth, current design.** `nginx-plain`'s `auth_basic` gate was replaced with Authentik's server-level `auth_request` (see "SSO at the hub level" below), and each browser container's own `CUSTOM_USER`/`PASSWORD` was removed at the same time — not kept as defense-in-depth, since Authentik's forward-auth is cookie-based, not header-based, so there was nothing left for nginx to forward that would also satisfy a container's own Basic Auth check; keeping it would have meant a second prompt with a credential that no longer synced with anything. `BROWSER_HUB_USER`/`BROWSER_HUB_PASSWORD` and `services/nginx-plain/docker-entrypoint.d/25-generate-browser-htpasswd.sh` (the script that generated `/etc/nginx/browser_htpasswd` from them) are both fully retired — removed from `homeserver.py`, every browser's `compose.yml`/`.env.example`, and `nginx-plain`'s own config.

**Real consequence of retiring the per-container gate: each browser's dev port (e.g. `8145` for Firefox — see [11-services-reference.md](../11-services-reference.md)'s Port Reference table) now has no authentication of its own at all.** It's not reachable from outside the LAN (dev ports are LAN-published, not exposed past this host — see the Gotchas section), but anyone on the LAN can now reach a browser directly with zero login, bypassing Authentik entirely. A known, accepted tradeoff rather than an oversight — worth knowing if you're used to the old per-container defense-in-depth layer. The "LAN isolation" section below is a *separate* containment measure (it stops a browser session, however someone got into it, from reaching other LAN devices) — it does not add auth back to the dev port.

## SUBFOLDER — the part that needed verifying

Each browser's `compose.yml` sets `SUBFOLDER=/firefox/` (etc.) — a `linuxserver/docker-baseimage-selkies` env var telling the app it's being served from a subpath rather than domain root, so its own generated asset/API/WebSocket URLs are subpath-aware. Upstream's docs only specify the format (`/subfolder/`, both slashes required) with no worked reverse-proxy example, so nginx-plain's location blocks were built on the standard "subpath-aware app" idiom: `proxy_pass http://firefox:3000;` with **no URI component** after the host, so the full incoming path (including `/firefox/...`) is forwarded unchanged rather than stripped — matching what a `SUBFOLDER`-aware app expects to receive.

**Verify this actually works after any Selkies base-image update**: load `https://browser.${DOMAIN}/firefox/`, confirm the desktop/browser UI renders (not a blank page or broken asset icons), and confirm the remote session actually responds to clicks (proves the WebSocket stream survived the subpath proxy, not just the initial HTML).

**Related gotcha, already fixed once**: every `proxy_pass` referencing a member container by hostname in `default.conf.template` — including the `/_status/<slug>` liveness-check locations the hub page's own JS polls — must use the `set $upstream http://firefox:3000; proxy_pass $upstream;` indirection, never a literal `proxy_pass http://firefox:3000;`. The literal form makes nginx resolve that hostname at config-load time, which fails hard (`nginx: [emerg] host not found in upstream`) if `nginx-plain` starts before that container exists on the network — a real race on a fresh `up browser`, not hypothetical (it happened: the `/_status/*` locations were written with the literal form and intermittently crashed `nginx-plain` on cold start until fixed).

## SSO at the hub level (Authentik forward-auth)

Done — the hub-level gate is Authentik forward-auth now, not Basic Auth. This was deferred once before (2026-08-19): **Authelia** was evaluated and passed on for the same job (would've given a real HTML login form — better Vaultwarden autofill, works from a mobile app too, not just the browser extension — at the cost of standing up a new ~1GB service), and **Authentik** was ruled out at the time for being an even heavier new service to add just for this. Neither tradeoff applies once Authentik is already running for other reasons, which it now is (see [authentik.md](authentik.md)) — the marginal cost of adding one more vhost to an *already-domain-level* provider is one nginx snippet, not a new service.

The design was intentionally SSO-migration-friendly from the start — auth centralized at **one** nginx server block instead of scattered across five — so the actual swap was small: replace this block's `auth_basic`/`auth_basic_user_file` lines with a server-level `auth_request` block (same shape as the other 5 forward-auth vhosts, see [authentik.md](authentik.md#forward-auth-for-other-services-nginx-auth_request)), plus the two internal outpost locations. The five browser containers, their `SUBFOLDER` routing, and the static hub page didn't change at all.

**One thing the other 5 forward-auth vhosts didn't need to handle: recursion.** Those vhosts put `auth_request` inside a specific `location / { }` block, with the internal `/outpost.goauthentik.io` and `@goauthentik_proxy_signin` locations as untouched siblings. Browser Hub's server-level `auth_request` (matching `auth_basic`'s original scope, so it covers every location automatically) *inherits* into those same two internal locations too — without `auth_request off;` explicitly set in both, the auth-check endpoint would need to check its own auth first, an infinite loop. Confirmed the fix works live: `/firefox/` (and every other member path) redirects to login when unauthenticated, and proxies through cleanly with a valid session — no recursion, no 500.

## LAN isolation

These 5 containers run real browsers reachable by anyone who can log in (via Authentik) or, per the dev-port gotcha below, anyone on the LAN at all — so they're isolated from this host's own LAN at the network level, independent of and in addition to the auth layer above. Each browser is pinned to a static IP on the `homeserver` Docker network (`172.18.255.240`-`244` for firefox/chromium/ungoogled-chromium/brave/mullvad-browser respectively, set via `networks.homeserver.ipv4_address` in each `compose.yml`) so firewall rules can target them by fixed address regardless of recreation. Internet access is untouched — only reaching this host's own LAN is blocked.

Two independent mechanisms are needed (confirmed live, both required — neither alone covers all traffic paths):

1. **`DOCKER-USER` iptables chain** — for genuine LAN devices (e.g. the router). This is the one chain Docker guarantees it never rewrites/reorders on daemon restart, unlike rules added directly to `FORWARD`. Matches the *original* (pre-NAT) destination via `conntrack --ctorigdst`, not a plain `-d` match — Docker's own DNAT for port-published containers rewrites the destination before `DOCKER-USER` ever sees the packet, so a plain match silently never fires.
2. **firewalld rich rule, `--zone=docker` specifically** — for this host's own published dev ports (e.g. Jellyfin on `:8096`). That traffic goes through a per-port `docker-proxy` userspace relay, delivered straight to `INPUT`, never traversing `FORWARD`/`DOCKER-USER` — mechanism 1 can't see it no matter how it's written. firewalld (not a raw `iptables -I INPUT` rule) is required because this host runs it and regenerates `INPUT` from its own config on every reload, which would silently drop a raw rule. `--zone=docker` specifically is required too — Fedora's docker-ce package creates a separate `docker` firewalld zone containing every docker/`br-*` bridge interface, apart from the host's default zone; a rich rule added without `--zone` lands in the default zone and is never evaluated for bridge traffic at all.

IPv6 is deliberately not covered — confirmed live, the browser containers have no IPv6 connectivity at all (the `homeserver` Docker network is IPv4-only), so there's nothing for an IPv6 rule to restrict.

**Install** (already applied on this host as of 2026-08-21):

```bash
sudo cp services/nginx-plain/browser-lan-block.sh /usr/local/bin/browser-lan-block.sh
sudo chmod +x /usr/local/bin/browser-lan-block.sh
sudo cp services/nginx-plain/browser-lan-block.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now browser-lan-block.service
```

The repo copy under `/mnt/mydata/...` is not run in place — if that path is a filesystem that can't hold real Unix execute permissions (e.g. a fuseblk/NTFS mount, the same root cause as an earlier Coolify SSH-keys incident, see `SERVICE_ROLLOUT.md`), systemd fails the unit outright (`Failed at step EXEC ... Permission denied`). Installing to `/usr/local/bin/` sidesteps that regardless of what filesystem the repo itself lives on.

```bash
# Manual apply/undo without the systemd unit, if ever needed:
/usr/local/bin/browser-lan-block.sh apply   # add the rules (default if no argument)
/usr/local/bin/browser-lan-block.sh undo    # remove everything the script has ever added
```

Both subcommands are idempotent — safe to run repeatedly, safe to run `undo` even if `apply` was never run. `LAN_SUBNET`, `HOST_LAN_IP`, and `FIREWALLD_ZONE` at the top of the script are set for this host's own network — edit them first if reusing this on a different host.

## Landing page presence

All six cards (the hub itself plus its five members) live under System → **Browsers**, a subcategory dedicated to this bundle (`services.json`'s `subcategoryLabels.browsers`). Each of the five browsers has its own real card with its own live status dot, driven by the normal per-card `/health/<slug>` mechanism every other card uses (see `services/landing/nginx.conf`) — nothing custom, so a future bundle member gets working status for free just by getting a card the normal way. Each member's public link points at its subpath under the *hub's* subdomain (`https://browser.${DOMAIN}/firefox/`, not `https://${DOMAIN}/browser/firefox` — that URL never existed and 404s, a bug caught and fixed once already) — set via `"sub": "browser"` + `"path": "firefox/"` (trailing slash required — nginx's `location /firefox/ { ... }` is a prefix match) on each member's `services.json` entry, which `buildCard()` combines as `https://${sub}.${DOMAIN}/${path}` before falling back to the default `https://${sub}.${DOMAIN}`. The hub's own card needs neither field — its slug already equals its subdomain.

The hub's own card (`services.json` slug `browser`) is marked `"virtual": true` — it has a landing-page presence but no `services/browser/compose.yml`; `homeserver.py` excludes `virtual` entries from `SERVICES_MIN`/`CORE`/`DAILY`/`OFFICE`/`AUTOMATION_AI`/`EXTRA`/`MANUAL` and from automatic category/subcategory `SERVICE_GROUPS` derivation, so `up all`/`up group:browsers`/etc. never try to docker-compose a directory that doesn't exist.

## Gotchas

- **`RESTART_APP=true` is set on every browser** — compensates for `HARDEN_DESKTOP` above disabling the terminal and xdg-open. Without it, accidentally closing the browser *application itself* inside the remote desktop (not just your own viewing tab — that's harmless, see "Access" above) would strand the session with no in-desktop way to relaunch it, short of restarting the whole container. This watchdog auto-relaunches the main app whenever it exits.
- **Dev-port direct access bypasses the hub entirely, with no auth of its own at all now.** Each browser's `compose.dev.yml` still exposes its own host port (Firefox `8145`, Chromium `8146`, etc.) for local debugging convenience. Before the Authentik migration this path was still gated by the container's own `CUSTOM_USER`/`PASSWORD`; that gate was removed along with the rest of the per-container Basic Auth (see "Auth history" above), so a dev port is now completely open to whoever can reach it. Consistent with how every other service in this stack treats `dev` ports (LAN-trusted convenience, never published past this host) — but a bigger jump in practice for these five than for most, since they used to have a real credential prompt and now have none. See "LAN isolation" above for the mitigation that does apply here (limits what a session can reach, not who can start one).
- **Multi-user login is now real, not simulated.** The old shared-Basic-Auth design was explicitly single-user (one `BROWSER_HUB_USER`/`BROWSER_HUB_PASSWORD` for everyone). Authentik gives every person their own account instead — see [authentik.md](authentik.md) for user management. No script or config in this bundle enforces single-user anymore; that constraint is gone along with the htpasswd-generation script that used to enforce it.
- If you add a sixth browser later, it needs: its own `compose.yml`/`.env` (with `SUBFOLDER=/<slug>/`), a new `location /<slug>/ { ... }` block copied from an existing one in `default.conf.template`, and a new link on `services/nginx-plain/html/browser-hub/index.html` — the hub page is static, not generated from `services.json`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
