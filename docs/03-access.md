# 03 — Choose Access Method

[← Docker + Network](02-docker-network.md) | [Home](../setup.md) | [Next: Nginx Proxy Manager →](04-nginx.md)

---

This is the only branch in the setup. Choose based on your goal:

| | [Cloudflare Tunnel](03a-cloudflare.md) | [Tailscale](03b-tailscale.md) |
| --- | --- | --- |
| **Use case** | Production, public access | Testing, local/private access |
| **Domain required** | Yes (on Cloudflare) | No |
| **HTTPS** | Automatic via Cloudflare | No (HTTP via IP) |
| **Port forwarding** | Not needed | Not needed |
| **Mobile app URL** | `https://immich.yourdomain.com` | `http://100.x.x.x:2283` |
| **Setup time** | ~15 min | ~5 min |

---

## Path A — Cloudflare Tunnel (production)

Exposes services publicly via your domain with automatic HTTPS. No open ports needed.

**→ [03a — Cloudflare Tunnel + DNS](03a-cloudflare.md)**

---

## Path B — Tailscale (testing)

Private access via Tailscale IP. Services are only reachable on your tailnet — not public.

**→ [03b — Tailscale](03b-tailscale.md)**

---

Both paths rejoin at [04 — Nginx Proxy Manager](04-nginx.md). Complete your chosen path first, then continue from there.

---

[← Docker + Network](02-docker-network.md) | [Home](../setup.md) | [Next: Nginx Proxy Manager →](04-nginx.md)
