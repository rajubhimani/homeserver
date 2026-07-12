---
name: homeserver-reverse-proxy
description: Use when touching reverse-proxy config (nginx-plain, Nginx Proxy Manager), switching which proxy is active, or debugging an HTTP/HTTPS scheme-detection issue (redirect loops, mixed-content, CSP blocks).
---

# Reverse proxy

Two options — **run only one at a time**, both bind to port 80/443:

| Option | Service | Best for |
| --- | --- | --- |
| `nginx-plain` | Plain nginx | **Default** — config-file based, domain-templated, works with Cloudflare Tunnel |
| `nginx` | Nginx Proxy Manager | Optional — UI-based config, Let's Encrypt via UI |

**To switch to NPM:** replace `nginx-plain` with `nginx` in `SERVICES_MIN` in `homeserver.py`. Then edit `nginx-plain/templates/default.conf.template` — replace `yourdomain.com` with your domain (or rely on the `${DOMAIN}` envsubst that already runs at container start, per service).

## Traffic flow

```text
Browser → Cloudflare Edge (TLS) → cloudflared (container) → nginx / NPM :80 → <container>
```

Cloudflare terminates TLS. Internal traffic is plain HTTP. Both proxies resolve services by Docker container name on the `homeserver` network. `cloudflared` connects **outbound only** — no ports need to be opened on the firewall.

## Always hardcode `X-Forwarded-Proto: https`

Since Cloudflare always terminates TLS and every internal hop is plain HTTP, never use dynamic scheme detection (nginx `$scheme`, Caddy's default `header_up` behavior) for the `X-Forwarded-Proto` header — it will always evaluate to `http`, even though the original request was HTTPS. This breaks any backend that derives its own scheme from that header (e.g. Laravel apps generating absolute URLs, which then get blocked by browser CSP/mixed-content rules). Hardcode it instead:

- nginx: `proxy_set_header X-Forwarded-Proto https;`
- Caddy: `header_up X-Forwarded-Proto https` inside the `reverse_proxy` block

Apply this in every reverse proxy config that sits in front of a container: `nginx-plain/templates/default.conf.template`, plus any service's **own** internal nginx/Caddy config in front of its app. Find current examples of the latter with `find . -maxdepth 2 -iname "nginx.conf" -o -maxdepth 2 -iname "Caddyfile"` (excluding `landing/` and `nginx-plain/`, which aren't service-internal proxies) rather than trusting a fixed list — any service can grow one of these later.

**This header alone is often not sufficient** — many apps also need their own app-level setting confirming HTTPS: a trusted-proxies list, a force-HTTPS flag, or a base-URL setting the app uses to generate absolute links, with the exact name varying a lot by app/framework. Check that app's own docs rather than guessing, and grep `docs/services/*.md` for "reverse proxy" or "HTTPS" for worked examples already documented in this stack if you want a concrete pattern to compare against. This class of bug causes unhealthy/503/broken-links symptoms that look unrelated to the actual cause.

## Health check routes must set `Host`

If an app validates the `Host` header (trusted domains/allowed hosts/CSRF origin checks), a bare `proxy_pass $upstream/;` health check will silently 400 forever. Explicitly set `proxy_set_header Host localhost;` (or whatever the app trusts) on that specific location block. See `docs/services/nextcloud.md` for the incident this caused.
