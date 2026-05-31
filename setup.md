# Homeserver

> Self-hosted personal cloud on your own hardware.  
> Replaces Google Drive, Google Photos, Netflix, and more.  
> Family-ready with individual logins.

---

## What's in the stack

| Service | Purpose | Replaces |
| --- | --- | --- |
| Nextcloud | File storage + sharing | Google Drive |
| Immich | Photo management | Google Photos |
| Jellyfin | Media streaming | Netflix / Plex |
| Vaultwarden | Password manager | 1Password / LastPass |
| Paperless-ngx | Document management | Scansnap cloud |
| Stirling PDF | PDF toolkit | Adobe Acrobat |
| Mealie | Recipe manager | Recipe apps |
| Gitea | Git hosting | GitHub |
| Forgejo | Git hosting (Gitea fork) | GitHub |
| Uptime Kuma | Service monitoring | Pingdom |
| Dozzle | Docker log viewer | — |
| Nginx Proxy Manager | Reverse proxy + routing | Manual nginx config |
| Landing page | Service dashboard with live status | — |
| Cloudflare Tunnel | Public HTTPS access | Port forwarding |

---

## How traffic flows

```text
Browser → Cloudflare Edge (TLS) → cloudflared → NPM:80 → container
```

Cloudflare handles TLS. Traffic from the tunnel to NPM is plain HTTP internally.

---

## Requirements

- Any x86-64 machine (laptop, mini PC, old desktop)
- Minimum 4 GB RAM (8 GB+ recommended)
- One drive for OS + Docker (SSD preferred)
- One drive for data (internal or USB, formatted ext4)
- Ubuntu 24.04 LTS (or any Debian-based distro)
- A domain on Cloudflare — or use [Tailscale](docs/03b-tailscale.md) for local/testing access

---

## Setup path

Go through these in order. Each doc links to the next.

| # | Doc | What you do |
| --- | --- | --- |
| [01](docs/01-data-drive.md) | Prepare Data Drive | Format the data drive, mount it, create the folder structure |
| [02](docs/02-docker-network.md) | Docker + Shared Network | Install Docker, create the `homeserver` bridge network |
| [03](docs/03-access.md) | **Choose access method** | Pick Cloudflare (public) or Tailscale (private) — only do one |
| [03a](docs/03a-cloudflare.md) | ↳ Cloudflare Tunnel | Set up cloudflared + DNS for public HTTPS access |
| [03b](docs/03b-tailscale.md) | ↳ Tailscale | Private access by IP, no domain needed |
| [04](docs/04-nginx.md) | Nginx Proxy Manager | Install NPM, add proxy hosts so each service gets its own domain |
| [05](docs/05-nextcloud.md) | Nextcloud | File storage, family accounts, external storage |
| [06](docs/06-immich.md) | Immich | Photo backup, mobile app, face recognition (optional) |
| [07](docs/07-landing.md) | Landing Page | Service dashboard showing live status for all services |
| [08](docs/08-maintenance.md) | Maintenance | Monthly updates, health checks, remote management from Mac, troubleshooting |
| [09](docs/09-firewall.md) | Firewall | UFW rules, port binding strategy (dev vs prod) |
| [10](docs/10-new-services.md) | New Services | Add Jellyfin, Vaultwarden, Paperless, Stirling PDF, Mealie, Gitea, Uptime Kuma, Dozzle |
| [11](docs/11-services-reference.md) | Services Reference | All ports, NPM proxy host table, access list setup, per-service notes |
| [12](docs/12-vpn.md) | VPN Services | Optional: WireGuard (wg-easy), self-hosted Tailscale (headscale), OpenVPN |

**Start here → [01 — Prepare Data Drive](docs/01-data-drive.md)**

---

## Reference

Quick links for day-to-day use once the stack is running.

| Doc | When to use |
| --- | --- |
| [Services Reference](docs/11-services-reference.md) | Look up any service's port, NPM config, or setup notes |
| [Maintenance](docs/08-maintenance.md) | Update images, check health, troubleshoot |
| [VPN Services](docs/12-vpn.md) | Set up WireGuard / headscale / OpenVPN for remote access |
| [Docker Cheatsheet](docs/docker-cheatsheet.md) | Images, containers, volumes, networks, cleanup commands |

---

## Quick commands

```bash
# start everything
sh homeserver.sh dev up all

# start core only (dozzle, nginx, landing, nextcloud)
sh homeserver.sh dev up core

# start / stop one service
sh homeserver.sh dev up jellyfin
sh homeserver.sh dev down jellyfin

# follow logs
sh homeserver.sh dev logs nextcloud

# Immich with face recognition
sh homeserver.sh dev up immich --profile ml

# manual-only services (not included in 'all')
sh homeserver.sh dev up stirling-pdf
sh homeserver.sh dev down stirling-pdf
```

---

## Folder structure

```text
~/homeserver/
├── homeserver.sh
├── nginx/
├── nextcloud/
├── immich/
├── jellyfin/
├── vaultwarden/
├── paperless/
├── stirling-pdf/
├── stirling-pdf-lite/
├── mealie/
├── gitea/
├── forgejo/
├── uptime-kuma/
├── dozzle/
├── wg-easy/
├── headscale/
├── openvpn/
└── landing/
```

Data drive:

```text
/mnt/seagate/
├── nextcloud/
├── postgres-nextcloud/
├── immich/
├── postgres-immich/
├── jellyfin/
├── vaultwarden/
├── paperless/
├── stirling-pdf/
├── stirling-pdf-lite/
├── mealie/
├── gitea/
├── forgejo/
└── uptime-kuma/
```
