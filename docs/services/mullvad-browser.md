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

## No VPN routing — this is the browser app only

**This container does not route traffic through Mullvad's VPN network.** `compose.yml` has no VPN sidecar, no WireGuard config, no `gluetun`/VPN network mode — it's a plain container on the normal `homeserver` bridge network, same as every other browser in this bundle. What you get is only the Mullvad Browser *application*: its anti-fingerprinting patches and hardened default settings (see "Not the same thing as Tor Browser" above for the related Tor distinction). Traffic still egresses from this server's own IP, unencrypted by any VPN layer, exactly like Firefox/Chromium/Brave here. If you want actual VPN-routed traffic, that's a separate concern from this container entirely (e.g. a VPN client on the host or its own sidecar) — nothing here provides it.

## Using it day to day

Open `https://browser.${DOMAIN}/mullvad-browser/` (via the [Browser Hub](browser-hub.md) page) and use it like any remote desktop — the whole window is a video stream (Selkies), not a native embed. Reach for this one specifically when you want to look like a generic, hard-to-fingerprint browser (e.g. avoiding tracking-based paywalls or cross-site profiling) — for actually hiding *which* server the traffic comes from, see the caveat above, and for stronger anonymity, an actual Tor Browser or Tor-routed session (not provided by this stack — see "Not the same thing as Tor Browser" above) is the closer fit.

## Image tag and setup

Tracks `:latest`, same deliberate exception to this repo's pinned-version convention as the other browsers here — see [firefox.md](firefox.md#image-tag--deliberate-exception-to-this-repos-pinned-version-convention) for the full reasoning. Confirmed actively maintained at the time this was added (new releases roughly every 1-2 days).

Setup is via the Browser Hub as a whole — see [browser-hub.md](browser-hub.md)'s Setup section (`uv run homeserver.py dev up browser`). Login credentials, `SUBFOLDER=/mullvad-browser/` subpath routing, `HARDEN_DESKTOP=true`, and `RESTART_APP=true` all follow the same shared model documented there.

## Gotchas

- Same `shm_size: "1gb"` requirement as Firefox.
- **`LOCAL_NET`** — a Mullvad-Browser-specific env var not present on the other four images: a CIDR range (or ranges) to let the browser reach on your LAN despite its anti-fingerprinting network isolation. Left unset in `.env.example` unless you specifically need it.
- No app-specific CLI-flags env var documented for this image (unlike Chromium/Ungoogled Chromium's `CHROME_CLI`).

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
