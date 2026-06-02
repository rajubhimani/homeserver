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

> No SSL in NPM — Cloudflare handles TLS at the edge. Adding certs here causes double-encryption.

**Tailscale path:** No domains needed. Services are accessed directly by IP and port when using dev compose. If you want NPM routing with local DNS, add entries in Tailscale's MagicDNS or your local resolver.

→ See [11 — Services Reference](11-services-reference.md) for the full proxy host table (all domains, ports, and access list requirements).

---

[← Access Setup](03-access.md) | [Home](../setup.md) | [Next: Nextcloud →](05-nextcloud.md)
