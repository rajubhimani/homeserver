# Mullvad Browser

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** A hardened, anti-fingerprinting Firefox fork (built jointly by Mullvad and the Tor Project) running remotely — part of the [Browser Hub](browser-hub.md), for browsing that resists tracking/fingerprinting specifically.
**Port:** `8149` (host, dev-only direct access) → `3000` (container) | **Public access:** `https://browser.${DOMAIN}/mullvad-browser/` via the [Browser Hub](browser-hub.md), not its own subdomain | **Data:** `service_data/data/mullvad-browser/config/` | **Requires:** nothing (single container, no DB) | **Memory:** no hard limit set; measured idle ~418MB

---

## What it is

[`linuxserver/mullvad-browser`](https://docs.linuxserver.io/images/docker-mullvad-browser/) — same `docker-baseimage-selkies` family as [Firefox](firefox.md), same remote-desktop-in-a-browser mechanism. Firefox-based (not Chromium), so — like plain Firefox — it does **not** need `security_opt: seccomp:unconfined`. See Firefox's doc for the shared design rationale and [browser-hub.md](browser-hub.md) for the shared login/routing — this doc only covers what's specific here.

## Not the same thing as Tor Browser

Mullvad Browser is a hardened, anti-fingerprinting Firefox fork sharing Tor Browser's privacy-hardening patches — **it does not itself route traffic through the Tor network.** It reduces how trackable/fingerprintable your browser is; it does not anonymize your IP or traffic path the way actually using Tor does. This distinction is why Mullvad Browser was chosen here instead of an actual Tor Browser image: no well-maintained, official Tor Browser container exists for this stack (see [browser-hub.md](browser-hub.md)'s history — the only alternative found was a single-maintainer image on an older base, not the trusted `linuxserver.io` family the rest of this bundle uses).

## Image tag and setup

Tracks `:latest`, same deliberate exception to this repo's pinned-version convention as the other browsers here — see [firefox.md](firefox.md#image-tag--deliberate-exception-to-this-repos-pinned-version-convention) for the full reasoning. Confirmed actively maintained at the time this was added (new releases roughly every 1-2 days).

Setup is via the Browser Hub as a whole — see [browser-hub.md](browser-hub.md)'s Setup section (`uv run homeserver.py dev up browser`). Login credentials, `SUBFOLDER=/mullvad-browser/` subpath routing, `HARDEN_DESKTOP=true`, and `RESTART_APP=true` all follow the same shared model documented there.

## Gotchas

- Same `shm_size: "1gb"` requirement as Firefox.
- **`LOCAL_NET`** — a Mullvad-Browser-specific env var not present on the other four images: a CIDR range (or ranges) to let the browser reach on your LAN despite its anti-fingerprinting network isolation. Left unset in `.env.example` unless you specifically need it.
- No app-specific CLI-flags env var documented for this image (unlike Chromium/Ungoogled Chromium's `CHROME_CLI`).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
