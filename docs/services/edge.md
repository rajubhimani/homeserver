# Edge

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** The official Microsoft Edge running remotely, for Microsoft 365 and sites that insist on Edge — part of the [Browser Hub](browser-hub.md).
**Port:** `8160` (host, dev-only direct access) → `3000` (container) | **Public access:** `https://browser.${DOMAIN}/edge/` via the [Browser Hub](browser-hub.md), not its own subdomain | **Data:** `service_data/data/edge/config/` | **Requires:** nothing (single container, no DB) | **Memory:** no hard limit set; idle usage not yet measured (expect 300-700MB in use, ~4.5GB image on disk)

---

## What it is

[`linuxserver/msedge`](https://docs.linuxserver.io/images/docker-msedge/) — same `docker-baseimage-selkies` family as [Firefox](firefox.md), same remote-desktop-in-a-browser mechanism. See Firefox's doc for the shared design rationale and [browser-hub.md](browser-hub.md) for the shared login/routing — this doc only covers what's specific here.

Chromium-based, but runs **without** `security_opt: seccomp:unconfined` (unlike the older `chromium`/`brave` services) — LinuxServer's current compose example for this image doesn't ask for it, and it was verified launching under Docker's default seccomp profile on 2026-09-26. If a future image update ever fails to start the browser with a sandbox error, that's the first thing to check.

## Using it day to day

Open `https://browser.${DOMAIN}/edge/` (via the [Browser Hub](browser-hub.md) page). **Compatibility only.** Edge is patched quickly but is proprietary and sends usage data to Microsoft. Use it for Microsoft 365 quirks or Edge-only sites, not everyday browsing.

Safety rating and the reasoning behind it: see [browser-hub.md](browser-hub.md#browser-safety--whats-in-the-hub-and-whats-deliberately-not).

## Image tag and setup

Tracks `:latest`, same deliberate exception to this repo's pinned-version convention as the other browsers here — see [firefox.md](firefox.md#image-tag--deliberate-exception-to-this-repos-pinned-version-convention) for the full reasoning. Pick up new releases with `uv run homeserver.py prod update edge`.

Setup is via the Browser Hub as a whole — see [browser-hub.md](browser-hub.md)'s Setup section (`uv run homeserver.py dev up browser`). Login, `SUBFOLDER=/edge/` subpath routing, `HARDEN_DESKTOP=true`, and `RESTART_APP=true` all follow the same shared model documented there. Static IP `172.18.255.249` on the `homeserver` network (for the LAN-isolation firewall rules — see browser-hub.md's "LAN isolation" section).

## Gotchas

- Same `shm_size: "1gb"` requirement as Firefox (upstream's documented minimum for modern websites).
- **`EDGE_CLI`** — this image's CLI-flags env var (e.g. a start URL or extra Chromium flags). Left empty in `.env.example`.
- Slug/container/path are `edge`, but the upstream image is `lscr.io/linuxserver/msedge` — don't look for a `linuxserver/edge` image, it doesn't exist.
- Proprietary: usage/diagnostic data goes to Microsoft unless reduced in Edge's own privacy settings.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
