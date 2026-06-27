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
| GitLab CE | Full DevOps platform | GitHub / GitLab.com |
| Uptime Kuma | Service monitoring | Pingdom |
| Stalwart | Mail server (SMTP + IMAP) | Gmail / Fastmail |
| Snappymail | Webmail (fast, minimal) | Gmail web |
| Roundcube | Webmail (full-featured) | Gmail web |
| Syncthing | Peer-to-peer file sync | Dropbox Sync |
| Authentik | Identity provider / SSO | Okta / Auth0 |
| Ntfy | Push notifications | Pushover |
| Miniflux | RSS reader | Feedly |
| Audiobookshelf | Audiobooks + podcasts | Audible |
| Conduit | Matrix chat server | Discord / Slack |
| OpenProject | Project management | Jira / Asana |
| Plane | Issue tracking | Linear / Jira |
| Crater | Invoicing | FreshBooks |
| Dozzle | Docker log viewer | — |
| nginx-plain | Reverse proxy (default) | Manual nginx config |
| Nginx Proxy Manager | Reverse proxy (optional, UI-based) | — |
| Landing page | Service dashboard with live status | — |
| Cloudflare Tunnel | Public HTTPS access, no open ports | Port forwarding |

---

## How traffic flows

```text
Browser → Cloudflare Edge (TLS) → cloudflared → nginx-plain:80 → container
```

Cloudflare handles TLS. Internal traffic is plain HTTP.
`nginx-plain` resolves services by Docker container name on the `homeserver` network.

> **Optional:** replace `nginx-plain` with Nginx Proxy Manager (NPM) for a UI-based config
> and Let's Encrypt. See [04 — Nginx](docs/04-nginx.md).

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
| [04](docs/04-nginx.md) | Reverse proxy | nginx-plain (default) or Nginx Proxy Manager (optional UI) |
| [05](docs/05-nextcloud.md) | Nextcloud | File storage, family accounts, external storage |
| [06](docs/06-immich.md) | Immich | Photo backup, mobile app, face recognition (optional) |
| [07](docs/07-landing.md) | Landing Page | Service dashboard showing live status for all services |
| [08](docs/08-maintenance.md) | Maintenance | Monthly updates, health checks, remote management, troubleshooting |
| [09](docs/09-firewall.md) | Firewall | UFW rules, port binding strategy (dev vs prod) |
| [10](docs/10-new-services.md) | New Services | Add any service from the stack — step-by-step for each |
| [11](docs/11-services-reference.md) | Services Reference | All ports, proxy config, per-service notes |
| [12](docs/12-vpn.md) | VPN Services | Optional: WireGuard (wg-easy), self-hosted Tailscale (headscale), OpenVPN |

**Start here → [01 — Prepare Data Drive](docs/01-data-drive.md)**

---

## Reference

Quick links for day-to-day use once the stack is running.

| Doc | When to use |
| --- | --- |
| [Services Reference](docs/11-services-reference.md) | Look up any service's port, proxy config, or setup notes |
| [Maintenance](docs/08-maintenance.md) | Update images, check health, troubleshoot |
| [VPN Services](docs/12-vpn.md) | Set up WireGuard / headscale / OpenVPN for remote access |
| [Docker Cheatsheet](docs/docker-cheatsheet.md) | Images, containers, volumes, networks, cleanup commands |

---

## Quick commands

```bash
# Service tiers — MIN ⊂ CORE ⊂ ALL
sh homeserver.sh dev up min          # infrastructure only (dozzle, cloudflared, nginx-plain, landing)
sh homeserver.sh dev up core         # min + nextcloud
sh homeserver.sh dev up all          # everything (core + all extra services)

sh homeserver.sh dev down min        # stop min (reverse order)
sh homeserver.sh dev down core       # stop core (reverse order)
sh homeserver.sh dev down all        # stop everything

# Start / stop one service
sh homeserver.sh dev up jellyfin
sh homeserver.sh dev down jellyfin

# Follow logs
sh homeserver.sh dev logs nextcloud

# Immich with face recognition
sh homeserver.sh dev up immich --profile ml

# Pull latest images and recreate
sh homeserver.sh dev update all
sh homeserver.sh dev update running  # only currently running services

# Production (ports bound to 127.0.0.1 only)
sh homeserver.sh prod up all
```

---

## Folder structure

```text
~/homeserver/
├── homeserver.sh
├── .env                   ← set DOMAIN= here once
├── nginx-plain/           ← default reverse proxy
├── nginx/                 ← optional: Nginx Proxy Manager
├── cloudflared/
├── landing/
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
├── gitlab/
├── uptime-kuma/
├── dozzle/
├── stalwart/
├── snappymail/
├── roundcube/
├── syncthing/
├── authentik/
├── ntfy/
├── miniflux/
├── audiobookshelf/
├── conduit/
├── openproject/
├── plane/
├── crater/
├── wg-easy/
├── headscale/
└── openvpn/
```

Service data (gitignored):

```text
service_data/
├── nextcloud/        (postgres/, config/, data/, custom_apps/)
├── immich/           (upload/, postgres/)
├── jellyfin/         (config/, cache/)
├── vaultwarden/      (data/)
├── paperless/        (postgres/, app/)
├── stirling-pdf/     (configs/, logs/, customFiles/, pipeline/, tessdata/)
├── stirling-pdf-lite/ (configs/, logs/, customFiles/, pipeline/)
├── mealie/           (postgres/, data/)
├── gitea/            (postgres/, data/)
├── forgejo/          (postgres/, app/)
├── gitlab/           (config/, logs/, data/)
├── uptime-kuma/      (data/)
├── stalwart/         (data/)
├── snappymail/       (data/)
├── roundcube/        (data/)
├── syncthing/        (data/)
├── authentik/        (postgres/, media/, certs/, templates/)
├── ntfy/             (data/)
├── miniflux/         (postgres/)
├── audiobookshelf/   (config/, metadata/)
├── conduit/          (data/)
├── openproject/      (pgdata/, assets/)
├── plane/            (postgres/, uploads/, logs/)
└── crater/           (data/)
```
