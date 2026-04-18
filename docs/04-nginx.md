# 04 — Nginx Proxy Manager

[← Access Setup](03-access.md) | [Home](../setup.md) | [Next: Nextcloud →](05-nextcloud.md)

---

NPM is the single entry point for all HTTP traffic. It routes to each container by name via the shared `homeserver` Docker network.

## Start

The base `compose.yml` has no ports. Use the override matching your setup:

**Production (Cloudflare):**
```bash
cd ~/homeserver/nginx
docker compose -f compose.yml -f compose.prod.yml up -d
```

**Testing (Tailscale):**
```bash
cd ~/homeserver/nginx
docker compose -f compose.yml -f compose.dev.yml up -d
```

## Admin setup

Open the admin UI and change the default credentials immediately.

**Cloudflare path:** `http://localhost:81` (or SSH tunnel to server)  
**Tailscale path:** `http://100.x.x.x:81`

Default login: `admin@example.com` / `changeme`

## Add proxy hosts

Go to **Proxy Hosts → Add Proxy Host** for each service. The forward hostname is the Docker **container name** — NPM resolves it via the shared network.

### Cloudflare path

| Domain | Forward Hostname | Forward Port | Notes |
| --- | --- | --- | --- |
| `yourdomain.com` | `landing` | `80` | Dashboard |
| `nextcloud.yourdomain.com` | `nextcloud` | `80` | |
| `immich.yourdomain.com` | `immich-server` | `2283` | |
| `jellyfin.yourdomain.com` | `jellyfin` | `8096` | |
| `vaultwarden.yourdomain.com` | `vaultwarden` | `80` | |
| `paperless.yourdomain.com` | `paperless` | `8000` | |
| `stirling-pdf.yourdomain.com` | `stirling-pdf` | `8080` | |
| `mealie.yourdomain.com` | `mealie` | `9000` | |
| `gitea.yourdomain.com` | `gitea` | `3000` | |
| `uptime-kuma.yourdomain.com` | `uptime-kuma` | `3001` | |
| `dozzle.yourdomain.com` | `dozzle` | `8080` | |

> No SSL in NPM — Cloudflare handles TLS at the edge. Adding certs here causes double-encryption.

### Tailscale path

No domains needed. Services are accessed directly by IP and port when using dev compose. NPM is still used internally for routing consistency.

If you want NPM routing on Tailscale (with local DNS):

| Domain | Forward Hostname | Forward Port |
| --- | --- | --- |
| `nextcloud.home` | `nextcloud` | `80` |
| `immich.home` | `immich-server` | `2283` |
| `jellyfin.home` | `jellyfin` | `8096` |
| `vaultwarden.home` | `vaultwarden` | `80` |
| `paperless.home` | `paperless` | `8000` |
| `stirling-pdf.home` | `stirling-pdf` | `8080` |
| `mealie.home` | `mealie` | `9000` |
| `gitea.home` | `gitea` | `3000` |
| `uptime-kuma.home` | `uptime-kuma` | `3001` |
| `dozzle.home` | `dozzle` | `8080` |

Add these as custom DNS entries in Tailscale's MagicDNS or your local resolver. Otherwise use direct IP + port.

---

[← Access Setup](03-access.md) | [Home](../setup.md) | [Next: Nextcloud →](05-nextcloud.md)
