# Chromium

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** A real Chromium browser running on the server, controlled remotely — part of the [Browser Hub](browser-hub.md), for reaching sites that specifically need Chrome/Chromium (DevTools, Chrome-only extensions or web apps) that Firefox can't cover.
**Port:** `8146` (host, dev-only direct access) → `3000` (container) | **Public access:** `https://browser.${DOMAIN}/chromium/` via the [Browser Hub](browser-hub.md), not its own subdomain | **Data:** `service_data/data/chromium/config/` | **Requires:** nothing (single container, no DB) | **Memory:** no hard limit set; measured idle ~263MB

---

## What it is

[`linuxserver/chromium`](https://docs.linuxserver.io/images/docker-chromium/) — same `docker-baseimage-selkies` family as [Firefox](firefox.md), same remote-desktop-in-a-browser mechanism. See that doc for the shared design rationale (why remote-browser at all, what it does and doesn't get around) and [browser-hub.md](browser-hub.md) for the shared login/routing this container sits behind — this doc only covers what's Chromium-specific.

## Chromium-specific: `security_opt: seccomp:unconfined`

Unlike Firefox, this container needs `security_opt: - seccomp:unconfined` in `compose.yml` — Chromium's own internal sandbox uses syscalls modern Docker's default seccomp profile restricts. This is in upstream's own base compose example, not just a troubleshooting fallback. `HARDEN_DESKTOP=true` (disables sudo/terminals/xdg-open) is set alongside it specifically to offset some of the extra syscall surface this opens up, same reasoning as Firefox's.

## Image tag and setup

Tracks `:latest`, same deliberate exception to this repo's pinned-version convention as Firefox, same rationale (public-facing, benefits from current security patches, stateless — profile lives in `/config`, not the image). See [firefox.md](firefox.md#image-tag--deliberate-exception-to-this-repos-pinned-version-convention) for the full reasoning.

Setup is via the Browser Hub as a whole — see [browser-hub.md](browser-hub.md)'s Setup section (`uv run homeserver.py dev up browser`). Login credentials, `SUBFOLDER=/chromium/` subpath routing, and `RESTART_APP=true` all follow the same shared model documented there.

## Gotchas

- Same `shm_size: "1gb"` requirement as Firefox — modern JS-heavy sites need it.
- `CHROME_CLI` is the app-specific CLI-flags env var (not `CHROMIUM_CLI`) — matches upstream's own naming, left empty by default in `.env.example`'s "remaining env vars" block.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
