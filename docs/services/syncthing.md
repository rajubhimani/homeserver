# Syncthing

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Peer-to-peer file sync between devices, no cloud required.
**Port:** `8087` (host) → `8384` (container, web UI) — also publishes `22000/tcp`, `22000/udp`, `21027/udp` (device sync + LAN discovery) on all interfaces in both dev and prod, since peer connectivity needs to be reachable regardless of env | **Data:** `service_data/data/syncthing/data/` (your actual synced files — still Explorer-browsable) + named volume `syncthing-config` (Syncthing's own app settings, not your files — moved off the bind mount since nothing needs to browse it directly) | **Requires:** — | **Memory:** no hard limit set; measured idle ~25MB

## Setup

```bash
cp services/syncthing/.env.example services/syncthing/.env
uv run homeserver.py dev up syncthing
```

## First login

Browse to `http://<ip>:8087` (or `https://syncthing.${DOMAIN}/` in prod) — set a password immediately in **Settings → GUI**.

## Making another device actually sync with it

Running the container doesn't sync anything by itself — Syncthing only talks to devices that have explicitly added each other by their unique **Device ID**, and only shares folders both sides have explicitly agreed to.

**Get this server's Device ID:** in its web UI, top right **Actions → Show ID** — shows the ID string and a QR code (useful for scanning straight from a phone).

**On the other device, add this server:**

- **Desktop (Windows/macOS/Linux, official Syncthing client):** **Add Remote Device**, paste this server's Device ID (or use the client's own QR-scan option if it has a webcam), give it a name, pick which of *that device's* folders to offer it, save.
- **Android:** the original official Syncthing app was discontinued (final release December 2024 — the maintainer cited Google Play publishing becoming "hard to impossible" plus no remaining motivation to keep maintaining a Play-less app) and hasn't been revived since; still no new official app as of this check. Install **Syncthing-Fork** instead — the community-maintained continuation, available on [F-Droid](https://f-droid.org/packages/com.github.catfriend1.syncthingandroid/), [Google Play](https://play.google.com/store/apps/details?id=com.github.catfriend1.syncthingandroid) (a separate maintainer mirrors upstream there for Play-policy compliance), or its GitHub releases. Same add-device flow: paste the ID or scan the QR code.
- **iOS/iPadOS:** there's no first-party Syncthing app — Apple's background-execution model doesn't allow a true always-on sync daemon. **Möbius Sync** (App Store; free tier capped at 20MB of synced data, one-time purchase or the separate "Möbius Sync Pro" listing to remove that cap) is the commonly used Syncthing-protocol client for iPhone/iPad.

**Back on this server, accept the pairing:** within a minute or so of the other device adding this server's ID, a "device wants to connect" notification appears in this server's web UI — click it and confirm. Both sides then show each other as connected.

**Share a folder:** on whichever side already has the folder, open it → **Edit** → **Sharing** tab → check the newly-added device → **Save**. The *other* side gets a pending-folder notification — accept it and choose a local path to sync it into (this server's own folders live under `${DATA_ROOT}/data/`, bind-mounted to `/data` in the container; desktop clients default new folders to `~/Sync/<folder-name>`). Once both sides show the folder as "Up to Date," anything added on either device propagates to the other automatically — no further action needed per file.

**To offer a folder from this server**, it has to exist here first: **Add Folder**, point it at a path under `/data`, then share it with the other device as above.

## Using it day to day

- **Folder type** (set per-folder, per-device, under a folder's **Edit → General** tab): **Send & Receive** (default — changes flow both ways) vs **Send Only** / **Receive Only**, useful for a one-way backup target you don't want a buggy client accidentally overwriting from the other end.
- **Conflicts:** if the same file changes on two devices before they sync, Syncthing keeps both — the losing version is renamed to `<filename>.sync-conflict-<date>-<time>.<ext>` next to the original rather than silently discarded.
- **Recovering an overwritten/deleted file:** enable a folder's **File Versioning** (Edit → File Versioning, "Simple File Versioning" is the usual choice) — old versions get moved into a `.stversions` folder instead of being deleted outright, for a configurable number of revisions/days.

## Notes

- No central server — pure peer-to-peer
- **Health endpoint:** the compose healthcheck curls `http://localhost:8384/rest/noauth/health` inside the container every 30s — the one Syncthing REST route that needs no API key. Confirmed live against the running container (`docker exec syncthing curl -s http://localhost:8384/rest/noauth/health`): returns `{"status": "OK"}` with a 200.
- **Pinned image:** `lscr.io/linuxserver/syncthing:2.1.3` — the web UI's menu structure described above (Actions → Show ID, Add Remote Device, Add Folder, Settings → GUI) matches this version's own [GUI documentation](https://docs.syncthing.net/v2.1.0/intro/gui) and its release notes; re-check if the pinned tag ever moves to a new major/minor.
- **Auto-upgrade disabled on purpose:** Syncthing's own config defaults to checking `https://upgrades.syncthing.net` every 12h (`autoUpgradeIntervalH` in its config) and would self-replace its binary inside the container if a newer release exists — silently drifting from this repo's pinned image tag. `compose.yml` sets `STNOUPGRADE: 1` to disable that; version bumps happen by bumping the image tag instead, per this repo's normal convention.
- **Android app status verified via web research only** (searched the Syncthing community forum's own discontinuation announcement and current F-Droid/Google Play listings as of 2026-08-22) — nothing here was confirmed by actually installing a phone app in this sandbox.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
