# Vivaldi

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Vivaldi, a power-user Chromium browser (tab stacking, built-in mail and calendar, heavy customisation), running remotely — part of the [Browser Hub](browser-hub.md).
**Port:** `8161` (host, dev-only direct access) → `3000` (container) | **Public access:** `https://browser.${DOMAIN}/vivaldi/` via the [Browser Hub](browser-hub.md), not its own subdomain | **Data:** `service_data/data/vivaldi/config/` | **Requires:** nothing (single container, no DB) | **Memory:** no hard limit set; idle usage not yet measured (expect 300-700MB in use, ~4.5GB image on disk)

---

## What it is

[`linuxserver/vivaldi`](https://docs.linuxserver.io/images/docker-vivaldi/) — same `docker-baseimage-selkies` family as [Firefox](firefox.md), same remote-desktop-in-a-browser mechanism. See Firefox's doc for the shared design rationale and [browser-hub.md](browser-hub.md) for the shared login/routing — this doc only covers what's specific here.

Chromium-based, but runs **without** `security_opt: seccomp:unconfined` (unlike the older `chromium`/`brave` services) — LinuxServer's current compose example for this image doesn't ask for it, and it was verified launching under Docker's default seccomp profile on 2026-09-26. If a future image update ever fails to start the browser with a sandbox error, that's the first thing to check.

## Using it day to day

Open `https://browser.${DOMAIN}/vivaldi/` (via the [Browser Hub](browser-hub.md) page). Pick it for its interface and built-in tools. Rated 🟡 acceptable rather than ✅: it ships on Chromium's Extended Stable channel with newer security fixes backported, so patches do arrive but it's never on the newest Chromium.

Safety rating and the reasoning behind it: see [browser-hub.md](browser-hub.md#browser-safety--whats-in-the-hub-and-whats-deliberately-not).

## Image tag and setup

Tracks `:latest`, same deliberate exception to this repo's pinned-version convention as the other browsers here — see [firefox.md](firefox.md#image-tag--deliberate-exception-to-this-repos-pinned-version-convention) for the full reasoning. Pick up new releases with `uv run homeserver.py prod update vivaldi`.

Setup is via the Browser Hub as a whole — see [browser-hub.md](browser-hub.md)'s Setup section (`uv run homeserver.py dev up browser`). Login, `SUBFOLDER=/vivaldi/` subpath routing, `HARDEN_DESKTOP=true`, and `RESTART_APP=true` all follow the same shared model documented there. Static IP `172.18.255.250` on the `homeserver` network (for the LAN-isolation firewall rules — see browser-hub.md's "LAN isolation" section).

## Gotchas

- Same `shm_size: "1gb"` requirement as Firefox (upstream's documented minimum for modern websites).
- **`VIVALDI_CLI`** — this image's CLI-flags env var (e.g. a start URL or extra Chromium flags). Left empty in `.env.example`.
- Its built-in mail/calendar store data in this container's `/config` profile — so on this server, not your device. Back up accordingly (`down` snapshots it like any other service).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
