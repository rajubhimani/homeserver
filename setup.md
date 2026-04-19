# Homeserver — Setup Guide

> Self-hosted personal cloud on your own hardware  
> Replaces Google Drive, Google Photos, Netflix, and more  
> Family-ready with individual logins

---

## Stack

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
| Uptime Kuma | Service monitoring | Pingdom |
| Dozzle | Docker log viewer | — |
| Nginx Proxy Manager | Reverse proxy + routing | Manual nginx config |
| Landing page | Service dashboard with live status | — |
| Cloudflare Tunnel | Public HTTPS access | Port forwarding |
| Docker | Container runtime | Manual installs |

---

## Requirements

- Any x86-64 machine (laptop, mini PC, old desktop)
- Minimum 4GB RAM (8GB+ recommended)
- One drive for OS + Docker (SSD preferred)
- One drive for data (internal or USB, formatted ext4)
- Ubuntu 24.04 LTS (or any Debian-based distro)
- A domain on Cloudflare — or use [Tailscale](docs/03b-tailscale.md) for local/testing access

---

## Traffic Flow

```text
Browser → Cloudflare Edge (TLS) → cloudflared → NPM:80 → container
```

Cloudflare handles TLS termination. Traffic from the tunnel to NPM is plain HTTP internally.

---

## Folder Structure

```text
~/homeserver/
├── homeserver.sh          ← manage all services
├── nginx/
│   ├── compose.yml
│   ├── compose.dev.yml
│   └── compose.prod.yml
├── nextcloud/
│   ├── compose.yml
│   ├── compose.dev.yml
│   └── .env
├── immich/
│   ├── compose.yml
│   ├── compose.dev.yml
│   └── .env
├── jellyfin/
│   ├── compose.yml
│   ├── compose.dev.yml
│   ├── compose.prod.yml
│   └── .env
├── vaultwarden/
│   ├── compose.yml
│   ├── compose.dev.yml
│   ├── compose.prod.yml
│   └── .env
├── paperless/
│   ├── compose.yml
│   ├── compose.dev.yml
│   ├── compose.prod.yml
│   └── .env
├── stirling-pdf/
│   ├── compose.yml
│   ├── compose.dev.yml
│   ├── compose.prod.yml
│   └── .env
├── stirling-pdf-lite/
│   ├── compose.yml
│   ├── compose.dev.yml
│   ├── compose.prod.yml
│   └── .env
├── mealie/
│   ├── compose.yml
│   ├── compose.dev.yml
│   ├── compose.prod.yml
│   └── .env
├── gitea/
│   ├── compose.yml
│   ├── compose.dev.yml
│   ├── compose.prod.yml
│   └── .env
├── uptime-kuma/
│   ├── compose.yml
│   ├── compose.dev.yml
│   ├── compose.prod.yml
│   └── .env
├── dozzle/
│   ├── compose.yml
│   ├── compose.dev.yml
│   ├── compose.prod.yml
│   └── .env
└── landing/
    ├── docker-compose.yml
    ├── compose.dev.yml
    ├── compose.prod.yml
    ├── nginx.conf
    └── index.html
```

Data drive:

```text
/mnt/seagate/
├── nextcloud/
├── immich/
├── postgres-nextcloud/
├── postgres-immich/
├── jellyfin/
├── vaultwarden/
├── paperless/
├── stirling-pdf/
├── mealie/
├── gitea/
└── uptime-kuma/
```

---

## Phases

| # | Phase | Notes |
| --- | --- | --- |
| [01](docs/01-data-drive.md) | Prepare Data Drive | Format, fstab, folder structure |
| [02](docs/02-docker-network.md) | Docker + Shared Network | Install Docker, create `homeserver` network |
| [03](docs/03-access.md) | **Choose Access Method** | Cloudflare Tunnel (production) or Tailscale (testing) |
| [03a](docs/03a-cloudflare.md) | ↳ Cloudflare Tunnel + DNS | Public HTTPS via your domain |
| [03b](docs/03b-tailscale.md) | ↳ Tailscale | Private access by IP, no domain needed |
| [04](docs/04-nginx.md) | Nginx Proxy Manager | Reverse proxy, routes traffic to containers |
| [05](docs/05-nextcloud.md) | Nextcloud | File storage, family accounts |
| [06](docs/06-immich.md) | Immich | Photo backup, mobile apps |
| [07](docs/07-landing.md) | Landing Page | Service dashboard with live status |
| [08](docs/08-maintenance.md) | Maintenance | Updates, troubleshooting, quick reference |
| [09](docs/09-firewall.md) | Firewall | UFW rules + compose port bindings per path |
| [10](docs/10-new-services.md) | New Services | Jellyfin, Vaultwarden, Paperless, and more |
| [11](docs/11-services-reference.md) | Services Reference | All services, ports, NPM proxy config, notes |

---

**Start here → [01 — Prepare Data Drive](docs/01-data-drive.md)**
