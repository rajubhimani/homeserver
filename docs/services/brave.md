# Brave

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** A real Brave browser running on the server, controlled remotely — part of the [Browser Hub](browser-hub.md). Brave's own ad-blocking/tracker-blocking is on by default, on top of everything else remote-browsing already gets you.
**Port:** `8148` (host, dev-only direct access) → `3000` (container) | **Public access:** `https://browser.${DOMAIN}/brave/` via the [Browser Hub](browser-hub.md), not its own subdomain | **Data:** `service_data/data/brave/config/` | **Requires:** nothing (single container, no DB) | **Memory:** no hard limit set; measured idle ~442MB

---

## What it is

[`linuxserver/brave`](https://docs.linuxserver.io/images/docker-brave/) — same `docker-baseimage-selkies` family as [Firefox](firefox.md) and [Chromium](chromium.md), same remote-desktop-in-a-browser mechanism. Brave is itself Chromium-based, so it shares Chromium's `security_opt: seccomp:unconfined` requirement (see [chromium.md](chromium.md)). See Firefox's doc for the shared design rationale and [browser-hub.md](browser-hub.md) for the shared login/routing — this doc only covers what's specific here.

## Image tag and setup

Tracks `:latest`, same deliberate exception to this repo's pinned-version convention as the other browsers here — see [firefox.md](firefox.md#image-tag--deliberate-exception-to-this-repos-pinned-version-convention) for the full reasoning.

Setup is via the Browser Hub as a whole — see [browser-hub.md](browser-hub.md)'s Setup section (`uv run homeserver.py dev up browser`). Login credentials, `SUBFOLDER=/brave/` subpath routing, `HARDEN_DESKTOP=true`, and `RESTART_APP=true` all follow the same shared model documented there.

## Gotchas

- Same `seccomp:unconfined`/`shm_size: "1gb"` requirements as Chromium (Brave is Chromium-based).
- **No app-specific CLI-flags env var exists for this image** (unlike Chromium/Ungoogled Chromium's `CHROME_CLI`) — upstream's own docs don't document one, so `.env.example` doesn't carry a stale/guessed var for it.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
