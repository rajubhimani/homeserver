# Zen

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Zen Browser — an open-source Firefox fork focused on design and customizability (vertical tabs, split view, workspaces) running remotely — part of the [Browser Hub](browser-hub.md).
**Port:** `8157` (host, dev-only direct access) → `3000` (container) | **Public access:** `https://browser.${DOMAIN}/zen/` via the [Browser Hub](browser-hub.md), not its own subdomain | **Data:** `service_data/data/zen/config/` | **Requires:** nothing (single container, no DB) | **Memory:** no hard limit set; idle usage not yet measured

---

## What it is

[`linuxserver/zen`](https://docs.linuxserver.io/images/docker-zen/) — same `docker-baseimage-selkies` family as [Firefox](firefox.md), same remote-desktop-in-a-browser mechanism. Firefox-based (not Chromium), so it does **not** need `security_opt: seccomp:unconfined`. See Firefox's doc for the shared design rationale and [browser-hub.md](browser-hub.md) for the shared login/routing — this doc only covers what's specific here.

## Using it day to day

Open `https://browser.${DOMAIN}/zen/` (via the [Browser Hub](browser-hub.md) page). Same Firefox engine and site compatibility as plain Firefox, with a different layout — pick it if you prefer vertical tabs/workspaces. It isn't more private or hardened than Firefox by default; for that, use [LibreWolf](librewolf.md) or [Mullvad Browser](mullvad-browser.md).

## Image tag and setup

Tracks `:latest`, same deliberate exception to this repo's pinned-version convention as the other browsers here — see [firefox.md](firefox.md#image-tag--deliberate-exception-to-this-repos-pinned-version-convention) for the full reasoning.

Setup is via the Browser Hub as a whole — see [browser-hub.md](browser-hub.md)'s Setup section (`uv run homeserver.py dev up browser`). Login, `SUBFOLDER=/zen/` subpath routing, `HARDEN_DESKTOP=true`, and `RESTART_APP=true` all follow the same shared model documented there. Static IP `172.18.255.246` on the `homeserver` network (for the LAN-isolation firewall rules — see browser-hub.md's "LAN isolation" section).

## Gotchas

- Same `shm_size: "1gb"` requirement as Firefox (upstream's documented minimum for modern websites).
- No app-specific CLI-flags env var documented for this image (unlike LibreWolf's `LIBREWOLF_CLI` or Chromium's `CHROME_CLI`).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
