# LibreWolf

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** A privacy-hardened Firefox fork (telemetry removed, uBlock Origin built in, stricter privacy defaults) running remotely — part of the [Browser Hub](browser-hub.md).
**Port:** `8156` (host, dev-only direct access) → `3000` (container) | **Public access:** `https://browser.${DOMAIN}/librewolf/` via the [Browser Hub](browser-hub.md), not its own subdomain | **Data:** `service_data/data/librewolf/config/` | **Requires:** nothing (single container, no DB) | **Memory:** no hard limit set; idle usage not yet measured

---

## What it is

[`linuxserver/librewolf`](https://docs.linuxserver.io/images/docker-librewolf/) — same `docker-baseimage-selkies` family as [Firefox](firefox.md), same remote-desktop-in-a-browser mechanism. Firefox-based (not Chromium), so it does **not** need `security_opt: seccomp:unconfined`. See Firefox's doc for the shared design rationale and [browser-hub.md](browser-hub.md) for the shared login/routing — this doc only covers what's specific here.

## Using it day to day

Open `https://browser.${DOMAIN}/librewolf/` (via the [Browser Hub](browser-hub.md) page). Reach for this one when you want Firefox compatibility with tracking protection turned up by default and no Mozilla telemetry. Its stricter defaults (resist-fingerprinting, cookies cleared on close) mean some sites may ask you to log in again every session, or behave slightly differently than in plain Firefox — use plain Firefox for those.

Unlike [Mullvad Browser](mullvad-browser.md), LibreWolf doesn't try to make every user look identical; it's a hardened everyday browser, not an anti-fingerprinting uniform.

## Image tag and setup

Tracks `:latest`, same deliberate exception to this repo's pinned-version convention as the other browsers here — see [firefox.md](firefox.md#image-tag--deliberate-exception-to-this-repos-pinned-version-convention) for the full reasoning.

Setup is via the Browser Hub as a whole — see [browser-hub.md](browser-hub.md)'s Setup section (`uv run homeserver.py dev up browser`). Login, `SUBFOLDER=/librewolf/` subpath routing, `HARDEN_DESKTOP=true`, and `RESTART_APP=true` all follow the same shared model documented there. Static IP `172.18.255.245` on the `homeserver` network (for the LAN-isolation firewall rules — see browser-hub.md's "LAN isolation" section).

## Gotchas

- Same `shm_size: "1gb"` requirement as Firefox (upstream's documented minimum for modern websites).
- **`LIBREWOLF_CLI`** — this image's CLI-flags env var (the LibreWolf equivalent of Chromium's `CHROME_CLI`), e.g. a start URL. Left empty in `.env.example`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
