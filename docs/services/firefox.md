# Firefox

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** A real Firefox browser running on the server, controlled remotely from any device's own browser — for reaching sites that are blocked on your local device or network.
**Port:** `8145` (host, dev-only direct access) → `3000` (container) | **Public access:** `https://browser.${DOMAIN}/firefox/` via the [Browser Hub](browser-hub.md), not its own subdomain | **Data:** `service_data/data/firefox/config/` | **Requires:** nothing (single container, no DB) | **Memory:** no hard limit set; measured idle ~207MB

---

## What it is

[`linuxserver/firefox`](https://docs.linuxserver.io/images/docker-firefox/) runs a full Firefox instance inside a lightweight Linux desktop (Selkies), streamed to your browser over HTTP/WebSocket — no VNC client, no Guacamole wiring, no software to install on the client side. It's a single self-contained container with its own login-gated web UI, unlike Guacamole (which is a *gateway* to some other machine's existing VNC/RDP service — see [guacamole.md](guacamole.md)).

**What this does and doesn't solve:** pages render and network requests go out from *this server's* connection, not the device you're viewing them from — so it gets around restrictions enforced on your own device or local network (e.g. a phone's parental controls, a school/office Wi-Fi filter). It does **not** get around restrictions enforced further upstream of the home network itself (an ISP-level block, or DNS filtering applied to this server's own connection) — the traffic still has to leave this server's ISP link like any other request from this stack.

## Image tag — deliberate exception to this repo's pinned-version convention

Every other service in this stack pins an exact image version (see [CLAUDE.md](../../CLAUDE.md)). This one intentionally tracks `:latest` instead:

- The container is reachable from the public internet and renders arbitrary third-party web content — it benefits from picking up Firefox security patches as soon as they ship, not on whatever cadence someone remembers to bump a pin.
- It's stateless from an image-versioning standpoint: your session/profile lives in the `/config` volume, not the image, so there's nothing a version bump could silently break in stored data the way a database schema change might.

Practical effect: `uv run homeserver.py dev update firefox` alone is enough to stay current — no manual tag editing needed. Run it weekly (or wire it into a cron via the `schedule` skill) if you want a routine.

## Setup

```bash
cp services/firefox/.env.example services/firefox/.env
uv run homeserver.py dev up firefox
```

Open `https://browser.${DOMAIN}/` (prod, once DNS/the tunnel picks it up), log in via Authentik, and click Firefox — or `http://<host>:8145` for direct dev-only access (no login at all, bypasses both the hub and Authentik entirely — see "Auth model" below).

**`HARDEN_DESKTOP=true`** is set on the container — this is a public-facing container running a full desktop, so sudo, terminal emulators, and xdg/exo-open (which can launch other applications from a clicked link/file) are disabled to reduce what a compromised or malicious page inside the session could reach. See the image's env var docs for the individual `DISABLE_SUDO`/`DISABLE_TERMINALS`/`DISABLE_OPEN_TOOLS` flags this bundles if finer control is ever needed.

**`SUBFOLDER=/firefox/`** tells the app it's served from a subpath rather than domain root — required for it to work behind the hub's subpath routing. See [browser-hub.md](browser-hub.md)'s "SUBFOLDER" section for the nginx-side half of this and why it needed real testing, not just following upstream's docs.

**Reverse proxy needs WebSocket support**, same as Guacamole — the hub's `/firefox/` location block in `nginx-plain`'s `browser.${DOMAIN}` server sets `proxy_http_version 1.1`, `Upgrade`/`Connection: upgrade`, and a long `proxy_read_timeout` (`3600s`) so the remote-desktop stream doesn't get cut by the proxy on an idle session.

## Auth model

Public access goes through the [Browser Hub](browser-hub.md)'s Authentik login (SSO) first — see that doc's "Auth history" section for how this design changed over time. This container has **no login of its own anymore** — no `CUSTOM_USER`/`PASSWORD`, no Basic Auth. The dev port (`8145`) therefore bypasses all authentication entirely, not just the hub, when reached directly — see browser-hub.md's "LAN isolation" section for the network-level containment that applies instead. Anyone who reaches the container (via Authentik or the dev port) shares the *same* browser session simultaneously (like a screen-share) — this image has no concept of separate concurrent sessions per user. If multiple people each need their own isolated browser, the pattern is to run additional instances of this same service (own subpath/port/profile per person), not to share one.

## Data

`${DATA_ROOT}/config` holds the full browser profile (`/config` in the container: bookmarks, extensions, history, cookies) — small enough to stay in the default `service_data/data/firefox/` bucket rather than needing a separate media/cache root.

## Gotchas

- **`shm_size: "1gb"`** is required — without it, modern JS-heavy sites (including video sites) can crash or fail to render, per upstream's own docs.
- Upstream's generic image description warns of "privileged access to the host system" — this refers to the container's own internal root/desktop-session model, not the Docker `--privileged` flag or host device access. This compose file does not set `privileged: true` or add extra `cap_add`/`security_opt`.
- The landing page's `/health/browser` route (representing the whole hub, since the hub itself is a static page not a container) probes this container directly and expects a plain 200 — there's no auth gate on this container anymore to produce a 401 through. The container's own Docker healthcheck is a plain unauthenticated `curl` against the root path.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
