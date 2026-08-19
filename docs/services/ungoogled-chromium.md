# Ungoogled Chromium

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Chromium with Google's tracking/telemetry stripped out, running remotely — part of the [Browser Hub](browser-hub.md), for Chromium compatibility without the Google plumbing.
**Port:** `8147` (host, dev-only direct access) → `3000` (container) | **Public access:** `https://browser.${DOMAIN}/ungoogled-chromium/` via the [Browser Hub](browser-hub.md), not its own subdomain | **Data:** `service_data/data/ungoogled-chromium/config/` | **Requires:** nothing (single container, no DB) | **Memory:** ~1GB idle

---

## What it is

[`linuxserver/ungoogled-chromium`](https://docs.linuxserver.io/images/docker-ungoogled-chromium/) — same `docker-baseimage-selkies` family as [Firefox](firefox.md) and [Chromium](chromium.md), same remote-desktop-in-a-browser mechanism. See Firefox's doc for the shared design rationale and [browser-hub.md](browser-hub.md) for the shared login/routing — this doc only covers what's specific here.

## What "ungoogled" actually means

[Ungoogled Chromium](https://github.com/ungoogled-software/ungoogled-chromium) is upstream Chromium with Google API keys, tracking pixels, and telemetry hooks removed at the build level — not a different rendering engine, not different site compatibility, just Chromium without the parts that phone home. Same Chromium sandbox, same `security_opt: seccomp:unconfined` requirement as plain [Chromium](chromium.md).

## Image tag and setup

Tracks `:latest`, same deliberate exception to this repo's pinned-version convention as the other browsers here — see [firefox.md](firefox.md#image-tag--deliberate-exception-to-this-repos-pinned-version-convention) for the full reasoning.

Setup is via the Browser Hub as a whole — see [browser-hub.md](browser-hub.md)'s Setup section (`uv run homeserver.py dev up browser`). Login credentials, `SUBFOLDER=/ungoogled-chromium/` subpath routing, `HARDEN_DESKTOP=true`, and `RESTART_APP=true` all follow the same shared model documented there.

## Gotchas

Same as [Chromium](chromium.md)'s — `seccomp:unconfined` needed for the sandbox, `shm_size: "1gb"` needed for modern sites, `CHROME_CLI` (not a `UNGOOGLED_CHROMIUM_CLI`) is the app-specific CLI-flags var name.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
